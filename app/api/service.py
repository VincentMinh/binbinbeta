from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
import os
from datetime import datetime

from ..db.session import get_db
from ..db.models import User, ServiceRecord, Branch, Department, AttendanceRecord
from ..core.security import get_csrf_token
from ..core.utils import get_current_work_shift, VN_TZ
from ..core.config import logger
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy import cast, Date
from sqlalchemy.orm import joinedload

from fastapi.templating import Jinja2Templates

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục gốc của project 'app'
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tạo đường dẫn tuyệt đối đến thư mục templates
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

@router.get("", response_class=HTMLResponse)
def attendance_service_ui(request: Request, db: Session = Depends(get_db)):
    user_data = request.session.get("user")
    if not user_data:
        return RedirectResponse("/login", status_code=303)
    
    # Quản lý và KTV không có chức năng chấm dịch vụ
    if user_data.get("role") in ["quanly", "ktv", "admin", "boss"]:
        return RedirectResponse("/choose-function", status_code=303)

    # === LOGIC MỚI ĐỂ LẤY DANH SÁCH NHÂN VIÊN ĐÃ ĐIỂM DANH ===
    checker_id = user_data.get("id")
    work_date, _ = get_current_work_shift() # Lấy ngày làm việc hiện tại

    # Tìm phòng ban "Buồng Phòng"
    buong_phong_dept = db.query(Department).filter(Department.role_code == 'buongphong').first()
    initial_employees = []

    if buong_phong_dept:
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

        initial_employees = [
            {
                "code": rec.employee_code_snapshot, 
                "name": rec.employee_name_snapshot, 
                "branch": rec.main_branch_snapshot, 
                "so_phong": "", "so_luong": "", "dich_vu": "", "ghi_chu": ""
            }
            for rec in recent_records
        ]
    
    # === LOGIC SỬA LỖI CHI NHÁNH BẮT ĐẦU TỪ ĐÂY ===

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
    
    # === KẾT THÚC SỬA LỖI ===

    csrf_token = get_csrf_token(request)
    
    response = templates.TemplateResponse("service.html", {
        "request": request,
        "branch_id": active_branch, # <-- Giá trị này giờ đã đúng
        "csrf_token": csrf_token,
        "user": user_data,
        "initial_employees": initial_employees,
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@router.post("/checkin_bulk")
async def service_checkin_bulk(request: Request, db: Session = Depends(get_db)):
    session_user = request.session.get("user")
    if not session_user:
        raise HTTPException(status_code=403, detail="Không có quyền điểm danh.")

    checker = db.query(User).filter(User.employee_code == session_user["code"]).first()
    if not checker:
        raise HTTPException(status_code=403, detail="Không tìm thấy người dùng thực hiện điểm danh.")

    try:
        raw_data = await request.json()
        if not isinstance(raw_data, list) or not raw_data:
            return {"status": "success", "inserted": 0}

        # Lấy branch_id của nơi làm việc từ payload
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

        new_service_records = []
        now_vn = datetime.now(VN_TZ)

        for rec in raw_data:
            ma_nv = rec.get("ma_nv")
            employee_snapshot = employee_map.get(ma_nv)

            if not employee_snapshot:
                logger.warning(f"Bỏ qua chấm dịch vụ cho mã NV không tồn tại: {ma_nv}")
                continue
            
            so_luong_str = str(rec.get("so_luong", ''))
            quantity_val = int(so_luong_str) if so_luong_str.isdigit() else None

            new_service_records.append(ServiceRecord(
                user_id=employee_snapshot.id,
                checker_id=checker.id,
                branch_id=branch_id_lam,
                is_overtime=bool(rec.get("la_tang_ca")), # Giữ lại để tương thích, dù có thể không dùng
                notes=rec.get("ghi_chu", ""),
                employee_code_snapshot=employee_snapshot.employee_code,
                employee_name_snapshot=employee_snapshot.name,
                role_snapshot=employee_snapshot.department.name if employee_snapshot.department else '',
                main_branch_snapshot=employee_snapshot.main_branch.branch_code if employee_snapshot.main_branch else '',
                service_datetime=now_vn,
                service_type=rec.get("dich_vu", "N/A"),
                room_number=rec.get("so_phong", ""),
                quantity=quantity_val
            ))

        if new_service_records:
            db.add_all(new_service_records)
            db.commit()

        return {"status": "success", "message": "Đã ghi nhận dịch vụ thành công."}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Lỗi khi lưu dịch vụ: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi khi lưu kết quả vào cơ sở dữ liệu.")