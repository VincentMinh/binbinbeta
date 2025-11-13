from fastapi import APIRouter, Request, Depends, BackgroundTasks, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import os
from typing import Optional, List
from datetime import datetime

from ..db.session import get_db
from ..db.models import User, AttendanceRecord, ServiceRecord, Branch, Department, AttendanceLog
from ..core.security import get_csrf_token, require_checked_in_user, validate_csrf
from ..core.utils import get_current_work_shift, VN_TZ, format_datetime_display
from ..core.config import logger, ROLE_MAP, BRANCHES
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import cast, Date, select, or_, and_
from sqlalchemy.orm import joinedload

from fastapi.templating import Jinja2Templates

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục gốc của project 'app'
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tạo đường dẫn tuyệt đối đến thư mục templates
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

@router.get("/attendance", response_class=HTMLResponse)
def attendance_ui(request: Request, db: Session = Depends(get_db)): # <-- THÊM Depends(get_db)
    user_data = request.session.get("user") or request.session.get("pending_user")
    if not user_data:
        return RedirectResponse("/login", status_code=303)
    
    # === LOGIC SỬA ĐỔI BẮT ĐẦU TỪ ĐÂY ===

    # 1. Ưu tiên hàng đầu: Chi nhánh đã chọn chủ động trong session (do GPS/chọn tay)
    active_branch = request.session.get("active_branch")

    if not active_branch:
        # 2. Nếu không có, query DB để lấy `last_active_branch`
        user_from_db = db.query(User).filter(User.id == user_data.get("id")).first()
        
        if user_from_db and user_from_db.last_active_branch:
            # Đây là nơi B10 của bạn sẽ được đọc
            active_branch = user_from_db.last_active_branch
        else:
            # 3. Nếu vẫn không có, dùng chi nhánh chính (mặc định) từ session
            active_branch = user_data.get("branch", "")
    
    # === KẾT THÚC SỬA ĐỔI ===

    csrf_token = get_csrf_token(request)
    
    response = templates.TemplateResponse("attendance.html", {
        "request": request,
        "branch_id": active_branch, # <-- Giờ đây giá trị này sẽ là "B10"
        "csrf_token": csrf_token,
        "user": user_data,
        "login_code": user_data.get("code", ""),
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def _auto_adjust_worksheet_columns(worksheet):
    """Helper function to adjust column widths of a worksheet."""
    for i, column_cells in enumerate(worksheet.columns, 1):
        max_length = 0
        column_letter = get_column_letter(i)
        # Also check header length
        if worksheet.cell(row=1, column=i).value:
            max_length = len(str(worksheet.cell(row=1, column=i).value))

        for cell in column_cells:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = (max_length + 2)
        worksheet.column_dimensions[column_letter].width = adjusted_width

@router.get("/api/employees/by-branch/{branch_code}", response_class=JSONResponse)
def get_employees_by_branch(branch_code: str, db: Session = Depends(get_db), request: Request = None):
    try:
        session_user = request.session.get("user") if request else None

        # Lấy thông tin chi nhánh từ DB
        branch = db.query(Branch).filter(Branch.branch_code == branch_code).first()
        if not branch:
            return JSONResponse(status_code=404, content={"detail": "Không tìm thấy chi nhánh."})

        # Xác định ca làm việc hiện tại
        _, shift_name = get_current_work_shift()
        current_shift_code = "CS" if shift_name == "day" else "CT"
        
        # Query cơ bản: lấy tất cả user thuộc chi nhánh này
        query = db.query(User).filter(User.main_branch_id == branch.id)

        # Áp dụng logic lọc theo vai trò và ca
        if session_user and session_user.get("role") == "letan":
            # Lễ tân thấy chính họ, và các vai trò khác cùng ca
            query = query.filter(
                or_(
                    User.id == session_user["id"],
                    and_(
                        User.shift == current_shift_code,
                        User.department_id.in_(
                            select(Department.id).where(Department.role_code.in_(['buongphong', 'baove']))
                        )
                    )
                )
            )
        elif not session_user or session_user.get("role") not in ["admin", "boss", "quanly"]:
            # Logic chung cho các vai trò khác (hoặc không đăng nhập): lọc theo ca
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

@router.get("/api/employees/search", response_class=JSONResponse)
def search_employees(
    q: str = "",
    request: Request = None,
    branch_code: Optional[str] = None, # Đổi tên từ branch_id để rõ ràng hơn
    only_bp: bool = False,
    login_code: Optional[str] = None,
    context: Optional[str] = None,
    role_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    if not q and context not in ['reporter_search', 'all_users_search']:
        return JSONResponse(content=[], status_code=400)
    # TỐI ƯU: Chỉ tìm kiếm khi có ít nhất 2 ký tự, trừ các context đặc biệt
    if len(q) < 2 and context not in ['reporter_search', 'all_users_search']:
        return JSONResponse(content=[])

    search_pattern = f"%{q}%"
    session_user = request.session.get("user") if request else None

    # Query cơ bản với joinedload để tối ưu
    base_query = db.query(User).options(
        joinedload(User.department),
        joinedload(User.main_branch)
    )

    # --- Lọc theo ngữ cảnh trang kết quả ---
    if session_user and session_user.get("role") not in ["admin", "boss"] and context == "results_filter":
        checker_id = session_user.get("id")

        # Lấy mã các nhân viên mà user này đã tạo bản ghi cho (dùng snapshot)
        att_codes_q = db.query(AttendanceRecord.employee_code_snapshot).filter(AttendanceRecord.checker_id == checker_id).distinct()
        svc_codes_q = db.query(ServiceRecord.employee_code_snapshot).filter(ServiceRecord.checker_id == checker_id).distinct()

        related_codes = {row[0] for row in att_codes_q.all()}
        related_codes.update({row[0] for row in svc_codes_q.all()})
        related_codes.add(session_user.get("code")) # Thêm chính mình

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

    # --- Tìm kiếm người báo cáo (Đồ thất lạc) ---
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
        # Trả về employee_code
        employee_list = [{"code": emp.employee_code, "name": emp.name} for emp in employees]
        return JSONResponse(content=employee_list)

    # --- Tìm kiếm tất cả user (Người thanh lý Đồ thất lạc) ---
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

    # --- Logic mặc định (trang điểm danh, admin/boss, etc.) ---
    else:
        query = base_query.filter(
            # SỬA: Ưu tiên tìm kiếm mã nhân viên chính xác, sau đó là tìm kiếm gần đúng
            # Ví dụ: tìm "B1" sẽ ra "B1" trước, không bị lẫn với "B10", "B11"
            or_(
                User.employee_code == q.upper(), # 1. Ưu tiên khớp chính xác
                User.employee_code.ilike(search_pattern),
                User.name.ilike(search_pattern)
            )
        )
        
        # Lọc theo chi nhánh bằng JOIN
        if branch_code and not only_bp:
            query = query.join(User.main_branch).filter(Branch.branch_code == branch_code)

        # Lọc theo vai trò bằng JOIN
        if role_filter:
            query = query.join(User.department).filter(Department.role_code == role_filter)

        employees = query.limit(50).all()

        # Logic lọc buồng phòng (dựa trên employee_code)
        if only_bp:
            employees = [emp for emp in employees if "BP" in (emp.employee_code or "").upper()]

        # Logic lọc bỏ Lễ tân (trừ người đang đăng nhập)
        is_admin_or_boss = session_user and session_user.get("role") in ["admin", "boss"]
        if not is_admin_or_boss:
            filtered_employees = []
            for emp in employees:
                role_code = emp.department.role_code if emp.department else ''
                if role_code == "letan":
                    if login_code and emp.employee_code == login_code:
                        filtered_employees.append(emp)
                else:
                    filtered_employees.append(emp)
            employees = filtered_employees

    # Trả về kết quả với cấu trúc dữ liệu mới
    employee_list = [
        {
            "code": emp.employee_code,
            "name": emp.name,
            # SỬA Ở ĐÂY: Trả về role_code thay vì name
            "department": emp.department.role_code if emp.department else '',
            "branch": emp.main_branch.branch_code if emp.main_branch else ''
        }
        for emp in employees[:20] # Giới hạn 20 kết quả cuối cùng
    ]
    return JSONResponse(content=employee_list)

@router.post("/checkin_bulk")
async def attendance_checkin_bulk( # Đổi tên hàm để rõ ràng hơn
    request: Request,
    db: Session = Depends(get_db)
):
    validate_csrf(request)

    session_user = request.session.get("user") or request.session.get("pending_user")
    if not session_user:
        raise HTTPException(status_code=403, detail="Không có quyền điểm danh.")

    # Lấy thông tin đầy đủ của người thực hiện điểm danh
    checker = db.query(User).filter(User.employee_code == session_user["code"]).first()
    if not checker:
        raise HTTPException(status_code=403, detail="Không tìm thấy người dùng thực hiện điểm danh.")

    try:
        raw_data = await request.json()
        if not isinstance(raw_data, list) or not raw_data:
            return {"status": "success", "inserted": 0}

        # Lấy branch_id của nơi làm việc
        branch_code_from_payload = raw_data[0].get("chi_nhanh_lam")
        branch_obj = db.query(Branch).filter(Branch.branch_code == branch_code_from_payload).first()
        if not branch_obj:
            raise HTTPException(status_code=400, detail=f"Chi nhánh làm việc không hợp lệ: {branch_code_from_payload}")
        branch_id_lam = branch_obj.id
        
        # Gom mã nhân viên để query một lần
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

            # Chỉ xử lý AttendanceRecord trong file này
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
        
        # Phần cập nhật last_checked_in_bp giữ nguyên logic cũ
        bp_codes = [rec.get("ma_nv") for rec in raw_data if "BP" in (rec.get("ma_nv") or "").upper()]
        if bp_codes:
            checker.last_checked_in_bp = bp_codes
        
        db.commit()

        return {"status": "success", "inserted": len(new_records)}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Lỗi khi lưu điểm danh: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi khi lưu điểm danh vào cơ sở dữ liệu.")

@router.get("/api/last-checked-in-bp", response_class=JSONResponse)
def get_last_checked_in_bp(request: Request, db: Session = Depends(get_db)):
    """
    API trả về danh sách nhân viên buồng phòng mà lễ tân đã điểm danh gần đây nhất
    trong ngày làm việc hiện tại.
    """
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập.")

    checker_id = user_data.get("id")
    work_date, _ = get_current_work_shift()

    # Tìm phòng ban "Buồng Phòng"
    buong_phong_dept = db.query(Department).filter(Department.role_code == 'buongphong').first()
    if not buong_phong_dept:
        return JSONResponse(content=[])

    # Lấy danh sách các bản ghi điểm danh do lễ tân này thực hiện
    # cho các nhân viên buồng phòng trong ngày làm việc hiện tại.
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
