from fastapi import APIRouter, Request, Depends, BackgroundTasks, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import os
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel # <-- THÊM IMPORT
from math import sin, cos, sqrt, atan2, radians # <-- THÊM IMPORT

from ..db.session import get_db
from ..db.models import User, AttendanceRecord, ServiceRecord, Branch, Department, AttendanceLog
from ..core.security import get_csrf_token, require_checked_in_user, validate_csrf
from ..core.utils import get_current_work_shift, VN_TZ, format_datetime_display
# SỬA DÒNG DƯỚI ĐỂ IMPORT TỌA ĐỘ
from ..core.config import logger, ROLE_MAP, BRANCHES, BRANCH_COORDINATES
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import cast, Date, select, or_, and_
from sqlalchemy.orm import joinedload

from fastapi.templating import Jinja2Templates

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục gốc của project 'app'
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tạo đường dẫn tuyệt đối đến thư mục templates
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

# === BẮT ĐẦU CODE THÊM MỚI ===

def haversine(lat1, lon1, lat2, lon2):
    """
    Tính khoảng cách (km) giữa 2 điểm GPS bằng công thức Haversine.
    """
    R = 6371  # Bán kính Trái Đất (km)
    
    # Chuyển đổi độ sang radians
    lat1_rad, lon1_rad = radians(lat1), radians(lon1)
    lat2_rad, lon2_rad = radians(lat2), radians(lon2)
    
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    
    # Công thức Haversine
    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    distance = R * c
    return distance

# Model Pydantic để nhận dữ liệu từ frontend
class GpsPayload(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None

class BranchSelectPayload(BaseModel):
    branch: str

# === KẾT THÚC CODE THÊM MỚI ===


@router.get("/", response_class=HTMLResponse) # <-- ĐÃ SỬA THÀNH "/"
def attendance_ui(request: Request, db: Session = Depends(get_db)):
    user_data = request.session.get("user") or request.session.get("pending_user")
    if not user_data:
        return RedirectResponse("/login", status_code=303)
    
    # === LOGIC LẤY CHI NHÁNH TỪ SESSION/DB ===
    active_branch = request.session.get("active_branch")

    if not active_branch:
        user_from_db = db.query(User).filter(User.id == user_data.get("id")).first()
        if user_from_db and user_from_db.last_active_branch:
            active_branch = user_from_db.last_active_branch
        else:
            active_branch = user_data.get("branch", "")
    
    csrf_token = get_csrf_token(request)
    
    response = templates.TemplateResponse("attendance.html", {
        "request": request,
        "branch_id": active_branch, 
        "csrf_token": csrf_token,
        "user": user_data,
        "login_code": user_data.get("code", ""),
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# === API DETECT-BRANCH ĐÃ SỬA LẠI HOÀN CHỈNH ===
@router.post("/api/detect-branch") # <-- SỬA TỪ @app VÀ BỎ /attendance
async def detect_branch(
    request: Request,
    payload: GpsPayload, # <-- Dùng Pydantic model
    db: Session = Depends(get_db)
):
    special_roles = ["quanly", "ktv", "boss", "admin"]

    user_data = request.session.get("user") or request.session.get("pending_user")
    user_in_db = None
    if user_data:
        # TỐI ƯU: Load sẵn main_branch để dùng
        user_in_db = db.query(User).options(
            joinedload(User.main_branch)
        ).filter(User.employee_code == user_data["code"]).first()

    # ===============================
    # 1. Role đặc biệt → bỏ qua GPS
    # ===============================
    if user_data and user_data.get("role") in special_roles:
        if user_in_db and user_in_db.main_branch:
            # SỬA LỖI LOGIC: Dùng main_branch.branch_code
            main_branch_code = user_in_db.main_branch.branch_code
            request.session["active_branch"] = main_branch_code
            user_in_db.last_active_branch = main_branch_code
            db.commit()
            return {"branch": main_branch_code, "distance_km": 0}

        return JSONResponse(
            {"error": "Không thể lấy chi nhánh chính. Vui lòng liên hệ quản trị."},
            status_code=400,
        )

    # ===============================
    # 2. Role thường → dùng GPS
    # ===============================
    lat, lng = payload.lat, payload.lng # <-- Lấy từ payload
    if lat is None or lng is None:
        # Nếu không có GPS, thử fallback về chi nhánh đã lưu
        if user_in_db and user_in_db.last_active_branch:
             request.session["active_branch"] = user_in_db.last_active_branch
             return {"branch": user_in_db.last_active_branch, "distance_km": 0}
        
        # Nếu không có gì cả, báo lỗi
        return JSONResponse(
            {"error": "Bạn vui lòng mở định vị (GPS) trên điện thoại để lấy vị trí."},
            status_code=400,
        )

    # Tìm chi nhánh trong bán kính 200m
    nearby_branches = []
    # SỬA: Dùng biến BRANCH_COORDINATES đã import từ config.py
    for branch, coords in BRANCH_COORDINATES.items():
        dist = haversine(lat, lng, coords[0], coords[1])
        if dist <= 0.2:  # trong 200m
            nearby_branches.append((branch, dist))

    if not nearby_branches:
        return JSONResponse(
            {"error": "Bạn đang ở quá xa khách sạn (ngoài 200m). Vui lòng điểm danh tại khách sạn."},
            status_code=403,
        )

    if len(nearby_branches) > 1:
        choices = [
            {"branch": b, "distance_km": round(d, 3)}
            for b, d in sorted(nearby_branches, key=lambda x: x[1])
        ]
        return {"choices": choices}

    chosen_branch, min_distance = nearby_branches[0]

    request.session["active_branch"] = chosen_branch
    if user_in_db:
        user_in_db.last_active_branch = chosen_branch
        db.commit()

    return {"branch": chosen_branch, "distance_km": round(min_distance, 3)}

# === API SELECT-BRANCH BỊ THIẾU ===
@router.post("/api/select-branch")
async def select_branch(
    payload: BranchSelectPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    API được gọi khi Lễ tân tự chọn 1 chi nhánh từ popup.
    Lưu lựa chọn này vào session và database.
    """
    user_data = request.session.get("user") or request.session.get("pending_user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Phiên làm việc hết hạn.")

    chosen_branch = payload.branch
    
    # Kiểm tra xem chi nhánh có hợp lệ không
    if chosen_branch not in BRANCH_COORDINATES:
         raise HTTPException(status_code=400, detail="Chi nhánh không hợp lệ.")

    # Lưu vào session
    request.session["active_branch"] = chosen_branch
    
    # Lưu vào DB
    user_in_db = db.query(User).filter(User.employee_code == user_data["code"]).first()
    if user_in_db:
        user_in_db.last_active_branch = chosen_branch
        db.commit()

    return {"status": "success", "branch": chosen_branch}


# --- CÁC API CÒN LẠI GIỮ NGUYÊN ---

@router.get("/api/employees/by-branch/{branch_code}", response_class=JSONResponse)
def get_employees_by_branch(branch_code: str, db: Session = Depends(get_db), request: Request = None):
    try:
        session_user = request.session.get("user") if request else None

        branch = db.query(Branch).filter(Branch.branch_code == branch_code).first()
        if not branch:
            return JSONResponse(status_code=404, content={"detail": "Không tìm thấy chi nhánh."})

        _, shift_name = get_current_work_shift()
        current_shift_code = "CS" if shift_name == "day" else "CT"
        
        query = db.query(User).options(
            joinedload(User.department),
            joinedload(User.main_branch)
        ).filter(User.main_branch_id == branch.id)

        if session_user and session_user.get("role") == "letan":
            letan_dept_id = db.query(Department.id).filter(Department.role_code == 'letan').scalar()
            buongphong_dept_id = db.query(Department.id).filter(Department.role_code == 'buongphong').scalar()
            baove_dept_id = db.query(Department.id).filter(Department.role_code == 'baove').scalar()

            # Lễ tân thấy chính họ, VÀ buồng phòng/bảo vệ cùng ca
            query = query.filter(
                or_(
                    User.id == session_user["id"],
                    and_(
                        User.shift == current_shift_code,
                        User.department_id.in_([buongphong_dept_id, baove_dept_id])
                    )
                )
            )
        elif not session_user or session_user.get("role") not in ["admin", "boss", "quanly"]:
            query = query.filter(User.shift == current_shift_code)
        
        employees = query.order_by(User.name).all()

        employee_list = [
            {
                "code": emp.employee_code, 
                "name": emp.name, 
                "department": emp.department.name if emp.department else '', 
                "branch": emp.main_branch.branch_code if emp.main_branch else ''
            }
            for emp in employees
        ]
        return JSONResponse(content=employee_list)

    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách nhân viên: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": f"Lỗi server: {str(e)}"})

# ... (API /api/employees/search giữ nguyên như file của bạn) ...
@router.get("/api/employees/search", response_class=JSONResponse)
def search_employees(
    q: str = "",
    request: Request = None,
    branch_code: Optional[str] = None, 
    only_bp: bool = False,
    login_code: Optional[str] = None,
    context: Optional[str] = None,
    role_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    if not q and context not in ['reporter_search', 'all_users_search']:
        return JSONResponse(content=[], status_code=400)
    if len(q) < 2 and context not in ['reporter_search', 'all_users_search']:
        return JSONResponse(content=[])

    search_pattern = f"%{q}%"
    session_user = request.session.get("user") if request else None

    base_query = db.query(User).options(
        joinedload(User.department),
        joinedload(User.main_branch)
    )

    if session_user and session_user.get("role") not in ["admin", "boss"] and context == "results_filter":
        checker_id = session_user.get("id")
        att_codes_q = db.query(AttendanceRecord.employee_code_snapshot).filter(AttendanceRecord.checker_id == checker_id).distinct()
        svc_codes_q = db.query(ServiceRecord.employee_code_snapshot).filter(ServiceRecord.checker_id == checker_id).distinct()
        related_codes = {row[0] for row in att_codes_q.all()}
        related_codes.update({row[0] for row in svc_codes_q.all()})
        related_codes.add(session_user.get("code")) 
        if not related_codes:
             return JSONResponse(content=[])
        query = base_query.filter(
            User.employee_code.in_(list(related_codes)),
            or_(
                User.employee_code.ilike(search_pattern),
                User.name.ilike(search_pattern)
            )
        )
        employees = query.limit(50).all()
    elif context == 'reporter_search':
        query = base_query.join(User.department).filter(
            ~Department.role_code.in_(['admin', 'boss'])
        ).filter(
            or_(
                User.employee_code.ilike(search_pattern),
                User.name.ilike(search_pattern)
            )
        )
        employees = query.limit(20).all()
        employee_list = [{"code": emp.employee_code, "name": emp.name} for emp in employees]
        return JSONResponse(content=employee_list)
    elif context == 'all_users_search':
        query = base_query.filter(
            or_(
                User.employee_code.ilike(search_pattern),
                User.name.ilike(search_pattern)
            )
        )
        employees = query.limit(20).all()
        employee_list = [{"code": emp.employee_code, "name": emp.name} for emp in employees]
        return JSONResponse(content=employee_list)
    else:
        query = base_query.filter(
            or_(
                User.employee_code == q.upper(),
                User.employee_code.ilike(search_pattern),
                User.name.ilike(search_pattern)
            )
        )
        if branch_code and not only_bp:
            query = query.join(User.main_branch).filter(Branch.branch_code == branch_code)
        if role_filter:
            query = query.join(User.department).filter(Department.role_code == role_filter)
        employees = query.limit(50).all()
        if only_bp:
            employees = [emp for emp in employees if "BP" in (emp.employee_code or "").upper()]
        
        is_admin_or_boss = session_user and session_user.get("role") in ["admin", "boss"]
        if not is_admin_or_boss:
            letan_dept_id = db.query(Department.id).filter(Department.role_code == 'letan').scalar()
            filtered_employees = []
            for emp in employees:
                if emp.department_id == letan_dept_id:
                    if login_code and emp.employee_code == login_code:
                        filtered_employees.append(emp)
                else:
                    filtered_employees.append(emp)
            employees = filtered_employees

    employee_list = [
        {
            "code": emp.employee_code,
            "name": emp.name,
            "department": emp.department.role_code if emp.department else '',
            "branch": emp.main_branch.branch_code if emp.main_branch else ''
        }
        for emp in employees[:20]
    ]
    return JSONResponse(content=employee_list)


# ... (API /checkin_bulk giữ nguyên như file của bạn) ...
@router.post("/checkin_bulk")
async def attendance_checkin_bulk(
    request: Request,
    db: Session = Depends(get_db)
):
    validate_csrf(request)
    session_user = request.session.get("user") or request.session.get("pending_user")
    if not session_user:
        raise HTTPException(status_code=403, detail="Không có quyền điểm danh.")
    checker = db.query(User).filter(User.employee_code == session_user["code"]).first()
    if not checker:
        raise HTTPException(status_code=403, detail="Không tìm thấy người dùng thực hiện điểm danh.")

    try:
        raw_data = await request.json()
        if not isinstance(raw_data, list) or not raw_data:
            return {"status": "success", "inserted": 0}

        branch_code_from_payload = raw_data[0].get("chi_nhanh_lam")
        branch_obj = db.query(Branch).filter(Branch.branch_code == branch_code_from_payload).first()
        if not branch_obj:
            raise HTTPException(status_code=400, detail=f"Chi nhánh làm việc không hợp lệ: {branch_code_from_payload}")
        branch_id_lam = branch_obj.id
        
        employee_codes = {rec.get("ma_nv") for rec in raw_data if rec.get("ma_nv")}
        employees_in_db = db.query(User).options(
            joinedload(User.main_branch), 
            joinedload(User.department)
        ).filter(User.employee_code.in_(employee_codes)).all()
        employee_map = {emp.employee_code: emp for emp in employees_in_db}
        
        new_records = []
        now_vn = datetime.now(VN_TZ)

        for rec in raw_data:
            ma_nv = rec.get("ma_nv")
            employee_snapshot = employee_map.get(ma_nv)
            if not employee_snapshot:
                logger.warning(f"Bỏ qua chấm công cho mã NV không tồn tại: {ma_nv}")
                continue

            new_records.append(AttendanceRecord(
                user_id=employee_snapshot.id,
                checker_id=checker.id,
                branch_id=branch_id_lam,
                is_overtime=bool(rec.get("la_tang_ca")),
                notes=rec.get("ghi_chu", ""),
                employee_code_snapshot=employee_snapshot.employee_code,
                employee_name_snapshot=employee_snapshot.name,
                role_snapshot=employee_snapshot.department.name if employee_snapshot.department else '',
                main_branch_snapshot=employee_snapshot.main_branch.branch_code if employee_snapshot.main_branch else '',
                attendance_datetime=now_vn,
                work_units=float(rec.get("so_cong_nv") or 1.0)
            ))

        if new_records:
            db.add_all(new_records)
        
        bp_codes = [rec.get("ma_nv") for rec in raw_data if "BP" in (rec.get("ma_nv") or "").upper()]
        if bp_codes:
            checker.last_checked_in_bp = bp_codes
        
        db.commit()

        # KIỂM TRA ĐẶC BIỆT: Nếu đây là lần đầu điểm danh sau khi quét QR
        # (pending_user tồn tại), chúng ta cần trả về redirect
        if request.session.get("pending_user"):
            token = raw_data[0].get("token") # Giả sử token được gửi kèm trong payload
            log = None
            if token:
                 log = db.query(AttendanceLog).filter(AttendanceLog.token == token).first()

            if log and not log.checked_in:
                log.checked_in = True
                db.commit()
            
            request.session["user"] = session_user
            request.session["after_checkin"] = "choose_function"
            request.session.pop("pending_user", None)
            return {"status": "success", "inserted": len(new_records), "redirect_to": str(request.url_for('choose_function'))}

        return {"status": "success", "inserted": len(new_records)}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Lỗi khi lưu điểm danh: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi khi lưu điểm danh vào cơ sở dữ liệu.")

# ... (API /api/last-checked-in-bp giữ nguyên như file của bạn) ...
@router.get("/api/last-checked-in-bp", response_class=JSONResponse)
def get_last_checked_in_bp(request: Request, db: Session = Depends(get_db)):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập.")

    checker_id = user_data.get("id")
    work_date, _ = get_current_work_shift()

    buong_phong_dept = db.query(Department).filter(Department.role_code == 'buongphong').first()
    if not buong_phong_dept:
        return JSONResponse(content=[])

    recent_records = db.query(
        AttendanceRecord.employee_code_snapshot,
        AttendanceRecord.employee_name_snapshot,
        AttendanceRecord.main_branch_snapshot
    ).join(User, AttendanceRecord.user_id == User.id
    ).filter(
        AttendanceRecord.checker_id == checker_id,
        User.department_id == buong_phong_dept.id,
        cast(AttendanceRecord.attendance_datetime, Date) == work_date
    ).distinct().all()

    employee_list = [
        {
            "code": rec.employee_code_snapshot,
            "name": rec.employee_name_snapshot,
            "branch": rec.main_branch_snapshot,
            "so_phong": "", "so_luong": "", "dich_vu": "", "ghi_chu": ""
        }
        for rec in recent_records
    ]
    return JSONResponse(content=employee_list)
