# app/main.py
# --------------------------------------------------------------------------
# Đây là điểm khởi đầu (entry point) của toàn bộ ứng dụng.
# Nhiệm vụ của file này là:
# 1. Khởi tạo ứng dụng FastAPI.
# 2. Cấu hình các thành phần toàn cục (middleware, static files).
# 3. "Lắp ráp" tất cả các module router (users, tasks, attendance...) vào ứng dụng.
# 4. Định nghĩa các tác vụ chạy nền khi khởi động (startup).
# --------------------------------------------------------------------------

# --- 1. IMPORT CÁC THƯ VIỆN CẦN THIẾT ---
import os
import atexit
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

# --- 2. IMPORT TỪ CÁC MODULE TRONG PROJECT ---
# Import các routers bạn đã tách ra
from .api import users, attendance, tasks, lost_and_found, choose_function, utils, calendar, qr_checkin, results, export, service, shift_report

# Import các thành phần cốt lõi và dịch vụ
from .core.config import settings, logger
from .core.utils import VN_TZ
from .db.session import SessionLocal, engine, Base
from .db.utils import reset_all_sequences, sync_employees_on_startup
from .services.missing_attendance_service import run_daily_absence_check
from .services.task_service import update_overdue_tasks_status
from .services.lost_and_found_service import update_disposable_items_status

# --- 3. KHỞI TẠO VÀ CẤU HÌNH ỨNG DỤNG FASTAPI ---
app = FastAPI(
    title="Bin Bin Hotel Management System",
    description="Hệ thống quản lý nội bộ khách sạn Bin Bin.",
    version="1.0.0"
)

# Cấu hình Middleware để quản lý session (quan trọng, chỉ cần làm một lần ở đây)
# SECRET_KEY được lấy từ file config để tăng tính bảo mật
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Cấu hình thư mục static để phục vụ file css, js, images...
# Đường dẫn được xây dựng một cách an toàn bằng os.path.join
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# --- 4. CÁC TÁC VỤ KHI KHỞI ĐỘNG (STARTUP) ---
@app.on_event("startup")
async def startup_event(): # Make it async
    """
    Hàm này sẽ được thực thi một lần duy nhất khi ứng dụng khởi động.
    Lý tưởng để đồng bộ database và khởi tạo các tác vụ nền.
    """
    logger.info("🚀 Bắt đầu quá trình khởi động ứng dụng...")

    Base.metadata.create_all(bind=engine)
    
    try:
        with SessionLocal() as db:
            # Đồng bộ database nếu cần
            reset_all_sequences(db)
            sync_employees_on_startup(db)

        # --- GIẢI PHÁP CHO VẤN ĐỀ TREO KHI DÙNG --reload ---
        # Chỉ khởi tạo scheduler trong tiến trình chính, không phải trong tiến trình reloader của uvicorn.
        # Uvicorn đặt biến môi trường này trong tiến trình con.
        if os.environ.get("UVICORN_RELOAD") != "true":
            # Lập lịch cho các tác vụ tự động (cron jobs)
            scheduler = BackgroundScheduler(timezone=str(VN_TZ))
            
            # Tác vụ kiểm tra và ghi nhận nhân viên vắng mặt, chạy lúc 7:05 sáng hàng ngày
            scheduler.add_job(
                run_daily_absence_check, 
                'cron', 
                hour=7, 
                minute=5, 
                misfire_grace_time=900, 
                id="daily_absence_check"
            )
            
            # Tác vụ cập nhật trạng thái "Quá hạn" cho công việc, chạy mỗi 30 phút
            scheduler.add_job(
                update_overdue_tasks_status, 
                'cron', 
                hour='0-23', 
                minute='*/30', 
                misfire_grace_time=300, 
                id="update_overdue_tasks"
            )
            
            scheduler.start()
            
            # Đảm bảo scheduler được tắt an toàn khi ứng dụng dừng
            atexit.register(lambda: scheduler.shutdown())
            logger.info("✅ Các tác vụ nền đã được lập lịch thành công.")

    except Exception as e:
        logger.error(f"❌ Đã xảy ra lỗi nghiêm trọng khi khởi động: {e}", exc_info=True)
    
    logger.info("✅ Startup hoàn tất: Ứng dụng đã sẵn sàng hoạt động.")

# --- 5. "LẮP RÁP" CÁC ROUTERS VÀO ỨNG DỤNG ---
# Gắn các router với tiền tố (prefix) URL tương ứng.
# Điều này giúp tổ chức code và URL một cách logic.
# Ví dụ: Mọi URL trong attendance.router sẽ bắt đầu bằng /attendance
app.include_router(attendance.router, prefix="/attendance", tags=["Attendance & Service"])
app.include_router(calendar.router, prefix="/attendance", tags=["Attendance & Service"])
app.include_router(qr_checkin.router, prefix="/attendance", tags=["QR Check-in"])
app.include_router(results.router, prefix="/attendance", tags=["Attendance & Service"])
app.include_router(service.router, prefix="/service", tags=["Attendance & Service"])
app.include_router(lost_and_found.router, prefix="/lost-and-found", tags=["Lost & Found"])
app.include_router(shift_report.router, prefix="/shift-report", tags=["Shift Report"])

# Các router dưới đây không cần prefix vì URL của chúng đã mang tính tuyệt đối
# Ví dụ: /login, /logout, /home, /choose-function
app.include_router(users.router, tags=["Users & Authentication"])
app.include_router(tasks.router, tags=["Tasks"]) # URL chính là /home
app.include_router(choose_function.router, tags=["Core UI"])
app.include_router(utils.router, tags=["Utilities"])
app.include_router(export.router, tags=["Export"])


# --- 6. ENDPOINT GỐC CỦA ỨNG DỤNG ---
@app.get("/", include_in_schema=False)
def root(request: Request):
    """
    Route gốc, chuyển hướng người dùng đến trang đăng nhập hoặc trang chọn chức năng
    tùy thuộc vào trạng thái đăng nhập trong session.
    """
    if request.session.get("user"):
        return RedirectResponse(url="/choose-function", status_code=303)
    return RedirectResponse(url="/login", status_code=303)