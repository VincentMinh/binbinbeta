from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload, contains_eager
from sqlalchemy import and_
import os
import uuid

from ..db.session import get_db
from ..db.models import User, AttendanceLog
from ..core.security import get_csrf_token
from ..core.utils import get_lan_ip, get_current_work_shift, _get_log_shift_for_user

from fastapi.templating import Jinja2Templates

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục gốc của project 'app'
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tạo đường dẫn tuyệt đối đến thư mục templates
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))


@router.get("/checkin")
def attendance_checkin(request: Request, token: str, db: Session = Depends(get_db)):
    """
    Endpoint được gọi khi người dùng quét mã QR.
    Xác thực token và hiển thị trang điểm danh nếu hợp lệ.
    """
    # Dùng options để load relationship 'user' cùng lúc, tránh query N+1
    log = db.query(AttendanceLog).options(joinedload(AttendanceLog.user)).filter(AttendanceLog.token == token).first()

    if not log:
        return templates.TemplateResponse(
            "qr_invalid.html",
            {"request": request, "message": "Mã QR không hợp lệ hoặc đã hết hạn."},
            status_code=400
        )

    if log.checked_in:
        return templates.TemplateResponse(
            "qr_invalid.html",
            {"request": request, "message": "Mã QR này đã được sử dụng để điểm danh và không còn hợp lệ."},
            status_code=403
        )

    # Lấy user trực tiếp từ relationship đã được load
    user = log.user
    if not user:
        return templates.TemplateResponse(
            "qr_invalid.html",
            {"request": request, "message": "Không tìm thấy người dùng liên kết với mã QR này."},
            status_code=404
        )

    # Lấy thông tin role và branch từ các bảng liên quan của user
    user_role_code = user.department.role_code if user.department else "khac"
    user_branch_code = user.main_branch.branch_code if user.main_branch else ""

    # Tạo dữ liệu session tạm thời cho người dùng đang chờ điểm danh
    user_data = {
        "id": user.id,
        "employee_id": user.employee_id,
        "code": user.employee_code,
        "role": user_role_code,
        "branch": user_branch_code,
        "name": user.name
    }

    request.session.pop("user", None)
    request.session["pending_user"] = user_data

    # Trả về trang điểm danh chính
    return templates.TemplateResponse("attendance.html", {
        "request": request,
        "branch_id": user_branch_code,
        "csrf_token": get_csrf_token(request),
        "user": user_data,
        "login_code": user.employee_code,
        "token": token
    })

@router.post("/checkin_success")
async def checkin_success(request: Request, db: Session = Depends(get_db)):
    """
    API được gọi từ frontend sau khi người dùng hoàn tất các thao tác trên UI điểm danh.
    Cập nhật trạng thái `checked_in` trong `AttendanceLog`.
    """
    session_user = request.session.get("pending_user") or request.session.get("user")
    if not session_user:
        return JSONResponse({"success": False, "error": "Không tìm thấy thông tin người dùng trong session."}, status_code=403)

    # Boss & Admin vào thẳng, không cần xử lý log
    if session_user.get("role") in ["boss", "admin"]:
        request.session["user"] = dict(session_user)
        request.session["after_checkin"] = "choose_function"
        request.session.pop("pending_user", None)
        return JSONResponse({"success": True, "redirect_to": str(request.url_for('choose_function'))})

    # Các role khác cần cập nhật AttendanceLog
    data = await request.json()
    token = data.get("token") or request.session.get("qr_token")

    if not token:
        return JSONResponse({"success": False, "error": "Không tìm thấy token điểm danh."}, status_code=400)

    log = db.query(AttendanceLog).filter(AttendanceLog.token == token).first()
    if not log:
        return JSONResponse({"success": False, "error": "Token không hợp lệ hoặc đã hết hạn."}, status_code=400)

    log.checked_in = True
    db.commit()

    # Cập nhật session chính thức
    request.session["user"] = session_user
    request.session["after_checkin"] = "choose_function"
    request.session.pop("pending_user", None)

    return JSONResponse({"success": True, "redirect_to": str(request.url_for('choose_function'))})

@router.get("/checkin_status")
async def checkin_status(request: Request, token: str, db: Session = Depends(get_db)):
    """
    API được máy tính (trang show_qr) gọi để kiểm tra xem điện thoại đã điểm danh thành công chưa.
    """
    # ... (code query) ...
    log = db.query(AttendanceLog).outerjoin(
        User, and_(AttendanceLog.user_id == User.id, User.is_active == True)
    ).options(contains_eager(AttendanceLog.user)).filter(AttendanceLog.token == token).first()

    if log and log.checked_in and log.user:
        # Đăng nhập cho user ở session của máy tính
        request.session["user"] = {
            "id": log.user.id, 
            "code": log.user.employee_code, 
            "name": log.user.name,
            "role": log.user.department.role_code if log.user.department else 'khac'
        }
        
        # === SỬA LỖI NGHIÊM TRỌNG ===
        # Đọc chi nhánh mới nhất (mà điện thoại vừa lưu) từ DB và cập nhật vào session của máy tính
        if log.user.last_active_branch:
            request.session["active_branch"] = log.user.last_active_branch
        # === KẾT THÚC SỬA LỖI ===

        request.session.pop("pending_user", None)
        request.session.pop("qr_token", None)
        return JSONResponse(content={"checked_in": True, "redirect_to": str(request.url_for('choose_function'))})

    return JSONResponse(content={"checked_in": False})

@router.get("/show_qr", response_class=HTMLResponse)
async def show_qr(request: Request, db: Session = Depends(get_db)):
    """
    Hiển thị trang QR code cho người dùng trên máy tính để bàn.
    Tạo hoặc lấy lại token QR cho ca làm việc hiện tại.
    """
    user_session = request.session.get("pending_user") or request.session.get("user")
    if not user_session:
        return RedirectResponse("/login", status_code=303)

    work_date, shift_name = get_current_work_shift()
    user_role = user_session.get("role")
    shift_value = _get_log_shift_for_user(user_role, shift_name)
    user_id = user_session.get("id")

    log = db.query(AttendanceLog).filter(
        AttendanceLog.user_id == user_id,
        AttendanceLog.work_date == work_date,
        AttendanceLog.shift == shift_value
    ).first()

    if log:
        if log.checked_in:
            # Nếu đã check-in, cập nhật session và chuyển hướng
            request.session["user"] = user_session
            request.session.pop("pending_user", None)
            return RedirectResponse("/choose-function", status_code=303)
        else:
            # Nếu log đã tồn tại nhưng chưa check-in, dùng lại token cũ
            qr_token = log.token
    else:
        # Nếu chưa có log, tạo mới
        qr_token = str(uuid.uuid4())
        log = AttendanceLog(
            user_id=user_id,
            work_date=work_date,
            shift=shift_value,
            token=qr_token,
            checked_in=False
        )
        db.add(log)
        db.commit()

    request.session["qr_token"] = qr_token

    # Xác định base_url để tạo QR code
    request_host = request.url.hostname
    port = request.url.port
    scheme = request.url.scheme

    if request_host in ["localhost", "127.0.0.1"]:
        lan_ip = get_lan_ip()
        base_url = f"{scheme}://{lan_ip}:{port}"
    else:
        base_url = str(request.base_url).strip("/")

    return templates.TemplateResponse("show_qr.html", {
         "request": request,
         "qr_token": qr_token,
         "base_url": base_url,
         "user": user_session
     })
