from fastapi import Request, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import secrets

# Import model User để truy vấn
from ..db.models import User, AttendanceLog
from ..db.session import SessionLocal
from .utils import get_current_work_shift
from .config import logger

# === HÀM MỚI ĐƯỢC CHUYỂN VÀO ===
def get_active_branch(request: Request, db: Session, user_data: dict) -> Optional[str]:
    """
    Xác định chi nhánh hoạt động của người dùng theo thứ tự ưu tiên:
    1. Chi nhánh từ session (vừa quét GPS trong phiên này).
    2. Chi nhánh hoạt động cuối cùng đã lưu trong DB.
    3. Chi nhánh mặc định của user (fallback).
    """
    # 1. Lấy từ session (ưu tiên cao nhất)
    active_branch = request.session.get("active_branch")
    if active_branch:
        return active_branch

    # 2. Lấy từ DB
    user_from_db = db.query(User).filter(User.id == user_data.get("id")).first()
    if user_from_db and user_from_db.last_active_branch:
        return user_from_db.last_active_branch

    # 3. Lấy từ chi nhánh mặc định trong session
    return user_data.get("branch")

def require_checked_in_user(request: Request):
    user = request.session.get("user")
    if not user:
        return False

    # Admin và Boss luôn được truy cập nếu đã đăng nhập
    if user.get("role") in ["admin", "boss"]:
        return True

    # Lấy ngày làm việc hiện tại, xử lý cả trường hợp trước 7h sáng
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

            # Cho phép vào nếu có log đã check-in trong DB hoặc vừa quét QR xong
            if log or request.session.get("after_checkin") == "choose_function":
                return True
        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra trạng thái đăng nhập trong middleware: {e}", exc_info=True)
            return False # An toàn là trên hết, nếu lỗi DB thì không cho vào

    return False

# --- CSRF Token Management ---
def generate_csrf_token():
    return secrets.token_urlsafe(32)

def get_csrf_token(request: Request):
    token = request.session.get("csrf_token")
    if not token:
        token = generate_csrf_token()
        request.session["csrf_token"] = token
    return token

def validate_csrf(request: Request):
    token = request.headers.get("X-CSRF-Token") or request.query_params.get("csrf_token")
    session_token = request.session.get("csrf_token")
    if not session_token or token != session_token:
        raise HTTPException(status_code=403, detail="CSRF token không hợp lệ")