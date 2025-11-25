# app/main.py
import os
import atexit
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

# --- IMPORT MODULES ---
# Đảm bảo file api/__init__.py đã export các router này
from .api import (
    users, attendance, tasks, lost_and_found, 
    choose_function, utils, calendar, qr_checkin, 
    results, export, service, shift_report
)

from .core.config import settings, logger
from .core.utils import VN_TZ
from .db.session import SessionLocal, engine, Base
from .db.utils import reset_all_sequences, sync_employees_on_startup
from .services.missing_attendance_service import run_daily_absence_check
from .services.task_service import update_overdue_tasks_status
from .services.lost_and_found_service import update_disposable_items_status

# --- KHỞI TẠO APP ---
app = FastAPI(
    title="Bin Bin Hotel Management System",
    description="Hệ thống quản lý nội bộ khách sạn Bin Bin.",
    version="1.0.0"
)

# --- MIDDLEWARE ---
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# --- STATIC FILES ---
static_dir = os.path.join(os.path.dirname(__file__), "static")
# Kiểm tra thư mục static có tồn tại không để tránh lỗi startup
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# --- STARTUP EVENT ---
@app.on_event("startup")
async def startup_event():
    """
    Khởi tạo DB và Scheduler khi ứng dụng bắt đầu.
    """
    logger.info("🚀 Bắt đầu quá trình khởi động ứng dụng...")

    # Tạo bảng nếu chưa có
    Base.metadata.create_all(bind=engine)
    
    try:
        # Dùng context manager để đảm bảo đóng session an toàn
        with SessionLocal() as db:
            reset_all_sequences(db)
            sync_employees_on_startup(db)

        # Logic Scheduler (chỉ chạy ở process chính để tránh duplicate khi dev reload)
        if os.environ.get("UVICORN_RELOAD") != "true":
            scheduler = BackgroundScheduler(timezone=str(VN_TZ))
            
            # 7:05 sáng hàng ngày check vắng mặt
            scheduler.add_job(
                run_daily_absence_check, 
                'cron', hour=7, minute=5, 
                misfire_grace_time=900, id="daily_absence_check"
            )
            
            # 30 phút/lần update task quá hạn
            scheduler.add_job(
                update_overdue_tasks_status, 
                'cron', hour='0-23', minute='*/30', 
                misfire_grace_time=300, id="update_overdue_tasks"
            )
            
            scheduler.start()
            atexit.register(lambda: scheduler.shutdown())
            logger.info("✅ Các tác vụ nền (Scheduler) đã được lập lịch.")

    except Exception as e:
        logger.error(f"❌ Lỗi khởi động: {e}", exc_info=True)
    
    logger.info("✅ Startup hoàn tất.")


# --- ROUTERS ---
# 1. Các router có prefix (tiền tố URL)
app.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
app.include_router(calendar.router, prefix="/attendance", tags=["Calendar"]) # Lưu ý: cùng prefix /attendance
app.include_router(qr_checkin.router, prefix="/attendance", tags=["QR Check-in"])
app.include_router(results.router, prefix="/attendance", tags=["Results"])
app.include_router(service.router, prefix="/service", tags=["Service"])
app.include_router(lost_and_found.router, prefix="/lost-and-found", tags=["Lost & Found"])
app.include_router(shift_report.router, prefix="/shift-report", tags=["Shift Report"])

# 2. Các router KHÔNG có prefix (Root level)
# QUAN TRỌNG: users.router chứa logic Login (/login), Logout (/logout)
app.include_router(users.router, tags=["Authentication"]) 
app.include_router(tasks.router, tags=["Tasks"])
app.include_router(choose_function.router, tags=["Core UI"])
app.include_router(utils.router, tags=["Utilities"])
app.include_router(export.router, tags=["Export"])


# --- ROOT ENDPOINT ---
@app.get("/", include_in_schema=False)
def root(request: Request):
    """
    Điều hướng người dùng về trang chủ hoặc đăng nhập
    """
    if request.session.get("user"):
        return RedirectResponse(url="/choose-function", status_code=303)
    return RedirectResponse(url="/login", status_code=303)
