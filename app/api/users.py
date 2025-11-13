from fastapi import APIRouter, Request, Form, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
import os
from urllib.parse import urlencode
import secrets

from ..db.session import get_db, SessionLocal
from ..db.models import User, Department, Branch, AttendanceLog
from ..core.utils import get_current_work_shift, _get_log_shift_for_user
from ..schemas.user import VerifyPasswordPayload # THÊM: Import schema mới
from ..core.config import logger # Import logger từ core
from ..services.user_service import sync_employees_from_source 
from ..employees import employees
from sqlalchemy import or_

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục app
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# Tạo đường dẫn tuyệt đối đến thư mục templates bên trong app
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

# router/api/users.py

@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    request.session.clear()

    # === TỐI ƯU: Gộp 3 query thành 1 ===
    # Sử dụng joinedload để lấy thông tin User, Department, và Branch trong cùng một lượt
    user = db.query(User).options(
        joinedload(User.department),
        joinedload(User.main_branch)
    ).filter(
        User.employee_code == username,
        User.is_active == True
    ).first()

    # --- Xác thực mật khẩu ---
    if not user or user.password != password:
        # Logic báo lỗi vẫn giữ nguyên, không cần thay đổi
        user_exists = db.query(User).options(joinedload(User.department)).filter(User.employee_code == username).first()
        guessed_role = ""
        if user_exists and user_exists.department:
            guessed_role = user_exists.department.role_code

        query = urlencode({
            "error": "Mã nhân viên hoặc mật khẩu sai",
            "role": guessed_role
        })
        return RedirectResponse(f"/login?{query}", status_code=303)

    # === THAY ĐỔI: Truy cập trực tiếp từ relationship, không cần query lại ===
    user_role_code = user.department.role_code if user.department else "khac"
    user_branch_code = user.main_branch.branch_code if user.main_branch else ""
    
    # Tạo dữ liệu session
    session_data = {
        "id": user.id,
        "employee_id": user.employee_id,
        "code": user.employee_code,
        "role": user_role_code,
        "branch": user_branch_code,
        "name": user.name
    }

    # --- Phần logic xử lý check-in phía dưới giữ nguyên ---
    if user_role_code in ["boss", "admin"]:
        request.session["user"] = session_data
        request.session["after_checkin"] = "choose_function"
        return RedirectResponse("/choose-function", status_code=303)

    work_date, shift_name = get_current_work_shift()
    shift_value = _get_log_shift_for_user(user_role_code, shift_name)

    log = db.query(AttendanceLog).filter_by(
        user_id=user.id,
        work_date=work_date,
        shift=shift_value
    ).first()

    if log and log.checked_in:
        request.session["user"] = session_data
        request.session.pop("pending_user", None)
        return RedirectResponse("/choose-function", status_code=303)
    
    # === CẢI TIẾN: Lấy và lưu chi nhánh hoạt động cuối cùng vào session ===
    # Ngay cả khi đã check-in, chúng ta vẫn cần biết chi nhánh hoạt động cuối cùng là gì.
    if user.last_active_branch:
        request.session["active_branch"] = user.last_active_branch

    user_agent = request.headers.get("user-agent", "").lower()
    is_mobile = any(k in user_agent for k in ["mobi", "android", "iphone", "ipad"])
    
    token = secrets.token_urlsafe(24)
    if not log:
        log = AttendanceLog(
            user_id=user.id,
            work_date=work_date,
            shift=shift_value,
            token=token,
            checked_in=False
        )
        db.add(log)
    else:
        log.token = token
    db.commit()
    
    request.session["pending_user"] = session_data
    request.session["qr_token"] = token
    
    if is_mobile:
        return RedirectResponse("/attendance/ui", status_code=303)
    else:
        return RedirectResponse("/attendance/show_qr", status_code=303)

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    user = request.session.get("user")
    if user:
        # Lấy ngày làm việc hiện tại (xử lý cả trường hợp trước 7h sáng)
        work_date, _ = get_current_work_shift()
        
        with SessionLocal() as db:
            try:
                # === THAY ĐỔI CHÍNH Ở ĐÂY ===
                # Query theo user_id và work_date
                log = db.query(AttendanceLog).filter(
                    AttendanceLog.user_id == user["id"],
                    AttendanceLog.work_date == work_date,
                    AttendanceLog.checked_in == True
                ).first()
                
                if log: # Nếu tìm thấy bất kỳ log nào đã check-in trong ngày làm việc
                    return RedirectResponse(url="/choose-function", status_code=303)
            except Exception as e:
                logger.error(f"Lỗi khi kiểm tra log đăng nhập trong /login: {e}", exc_info=True)

    # Phần còn lại của hàm giữ nguyên
    error = request.query_params.get("error", "")
    role = request.query_params.get("role", "")
    response = templates.TemplateResponse("login.html", {
        "request": request,
        "error": error,
        "role": role
    })
    response.headers["Cache-control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)

# Danh sách các bảng có cột id SERIAL cần reset sequence
TABLES_WITH_SERIAL_ID = ["tasks", "attendance_log", "attendance_records", "service_records", "lost_and_found_items"]

def reset_sequence(db, table_name: str, id_col: str = "id"):
    """
    Reset sequence cho bảng cụ thể, đảm bảo id không bị trùng.
    """
    from sqlalchemy import text
    seq_name = f"{table_name}_{id_col}_seq"
    sql = f"SELECT setval('{seq_name}', (SELECT COALESCE(MAX({id_col}), 0) + 1 FROM {table_name}), false)"
    try:
        db.execute(text(sql))
        db.commit()
        logger.info(f"Đã đồng bộ sequence cho bảng {table_name}")
    except Exception as e:
        logger.error(f"Lỗi khi reset sequence cho {table_name}: {e}", exc_info=True)

@router.get("/sync-employees")
def sync_employees_endpoint(request: Request):
    """
    Endpoint để đồng bộ lại dữ liệu nhân viên từ employees.py vào database.
    Chỉ cho phép admin hoặc boss thực hiện.
    """
    user = request.session.get("user")
    if not user or user.get("role") not in ["admin", "boss"]:
        raise HTTPException(status_code=403, detail="Chỉ admin hoặc boss mới được đồng bộ nhân viên.")
    with SessionLocal() as db:
        sync_employees_from_source(db=db, employees_source=employees, force_delete=True)
    return {"status": "success", "message": "Đã đồng bộ lại danh sách nhân viên từ employees.py."}

@router.get("/api/users/search-login-users", response_class=JSONResponse)
def search_login_users(q: str = "", db: Session = Depends(get_db)):
    """
    API để tìm kiếm người dùng có quyền đăng nhập (lễ tân, ql, ktv, admin, boss).
    Đã cập nhật để hoạt động với kiến trúc mới.
    """
    if not q:
        return JSONResponse(content=[])
    
    search_pattern = f"%{q}%"
    allowed_role_codes = ["letan", "quanly", "ktv", "admin", "boss"]
    
    # === THAY ĐỔI: JOIN với Department để lọc theo role_code ===
    users = db.query(User).join(User.department).filter(
        Department.role_code.in_(allowed_role_codes),
        or_(
            User.employee_code.ilike(search_pattern),
            User.name.ilike(search_pattern)
        )
    ).limit(20).all()
    
    # Trả về employee_code để làm giá trị
    user_list = [
        {"code": user.employee_code, "name": user.name}
        for user in users
    ]
    return JSONResponse(content=user_list)

@router.post("/api/users/verify-password", response_class=JSONResponse)
async def verify_current_user_password(
    request: Request,
    payload: VerifyPasswordPayload,
    db: Session = Depends(get_db)
):
    """
    API để xác thực mật khẩu của một người dùng có vai trò 'admin' hoặc 'boss'.
    Dùng cho các thao tác cần có sự phê duyệt của cấp quản lý cao nhất.
    """
    # SỬA: Tìm người dùng theo username từ payload
    user = db.query(User).options(joinedload(User.department)).filter(User.employee_code == payload.username).first()

    if not user:
        raise HTTPException(status_code=404, detail="Tên đăng nhập không tồn tại.")

    # SỬA: Kiểm tra vai trò của người dùng được xác thực
    user_role = user.department.role_code if user.department else None
    if user_role not in ['admin', 'boss']:
        raise HTTPException(status_code=403, detail="Tài khoản này không có quyền xác thực.")

    # SỬA: So sánh mật khẩu từ payload với mật khẩu trong DB
    if user.password == payload.password:
        return {"success": True, "message": "Xác thực thành công."}
    else:
        raise HTTPException(status_code=401, detail="Mật khẩu không chính xác.")

@router.get("/api/users/search-checkers", response_class=JSONResponse)
def search_checkers(q: str = "", db: Session = Depends(get_db)):
    """
    API để tìm kiếm người dùng có quyền điểm danh (lễ tân, ql, ktv, admin, boss).
    Đã cập nhật để hoạt động với kiến trúc mới.
    """
    if not q:
        return JSONResponse(content=[])
    
    search_pattern = f"%{q}%"
    allowed_role_codes = ["letan", "quanly", "ktv", "admin", "boss"]
    
    # === THAY ĐỔI: JOIN với Department để lọc theo role_code ===
    users = db.query(User).join(User.department).filter(
        Department.role_code.in_(allowed_role_codes),
        or_(
            User.employee_code.ilike(search_pattern),
            User.name.ilike(search_pattern)
        )
    ).limit(20).all()
    
    # Trả về employee_code để làm giá trị
    user_list = [
        {"code": user.employee_code, "name": user.name}
        for user in users
    ]
    return JSONResponse(content=user_list)