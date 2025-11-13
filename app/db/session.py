from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# === THAY ĐỔI DUY NHẤT Ở ĐÂY ===
# Import đối tượng `settings` từ file config mới
from ..core.config import settings

# Tạo engine kết nối đến database từ URL trong đối tượng settings
engine = create_engine(
    str(settings.DATABASE_URL), # <-- Chuyển đổi sang string
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    echo=False
)

# --- CÁC PHẦN CÒN LẠI GIỮ NGUYÊN VÌ ĐÃ RẤT TỐT ---

# Tạo một lớp Session để quản lý các phiên làm việc với DB
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class cho các model. Tất cả các model của bạn trong models.py
# sẽ kế thừa từ lớp Base này.
Base = declarative_base()

def get_db():
    """Dependency to get a DB session for FastAPI."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()