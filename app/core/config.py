import os
import logging
from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings
from typing import Dict, Any, Optional

class Settings(BaseSettings):
    """
    Quản lý cấu hình của ứng dụng bằng Pydantic.
    Tự động đọc các biến từ file .env bằng pydantic-settings.
    """
    # --- BIẾN MÔI TRƯỜNG & CẤU HÌNH ---
    SECRET_KEY: str = "a_very_secret_key_please_change_me_in_env_file"
    DATABASE_URL: PostgresDsn
    LOG_LEVEL: str = "INFO"

    @field_validator("DATABASE_URL", mode='before')
    def build_db_connection(cls, v: Optional[str]) -> str:
        if v is None:
            raise ValueError("DATABASE_URL is not set in .env file!")
        
        # Sửa prefix postgres:// -> postgresql://
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql://", 1)
        
        # Thêm sslmode=require cho Supabase
        if "pooler.supabase.com" in v and "sslmode" not in v:
            separator = "&" if "?" in v else "?"
            v += f"{separator}sslmode=require"
            
        return v

    class Config:
        case_sensitive = True
        env_file = ".env"

# Khởi tạo một đối tượng settings duy nhất để dùng trong toàn bộ ứng dụng
settings = Settings()


# --- CẤU HÌNH LOGGING ---
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("binbin-app")


# --- CÁC HẰNG SỐ CỦA ỨNG DỤNG ---
# Các giá trị này ít thay đổi và không nhạy cảm, có thể giữ ở đây.

# Danh sách các bộ phận cho công việc
DEPARTMENTS = ["Chưa phân loại", "Nội bộ", "Sơn nước", "Thợ hồ", "Thợ đá", "Máy lạnh", "Máy nước nóng", "Thợ sắt", "Nhôm kính", "Thang máy", "PCCC", "Bảo trì", "Bảo hành"]

# Danh sách này có thể được thay thế bằng cách query từ bảng `branches` nếu muốn linh hoạt hơn
BRANCHES = [
    "B1", "B2", "B3", "B5", "B6", "B7", "B8", "B9", "B10",
    "B11", "B12", "B14", "B15", "B16", "B17",
    "DI DONG", "KTV", "QL"
]

# Map để dịch trạng thái Đồ thất lạc sang tiếng Việt
STATUS_MAP = {
    "STORED": "Đang lưu giữ",
    "RETURNED": "Đã trả khách",
    "DISPOSED": "Thanh lý",
    "DISPOSABLE": "Có thể thanh lý",
    "DELETED": "Đã xoá",
}

# Map để dịch vai trò sang tiếng Việt
ROLE_MAP = {
    "letan": "Lễ tân", "buongphong": "Buồng Phòng", "quanly": "Quản lý",
    "ktv": "Kỹ thuật viên", "baove": "Bảo vệ", "boss": "Boss",
    "admin": "Admin", "khac": "Khác",
}

# Tọa độ GPS của các chi nhánh để điểm danh
BRANCH_COORDINATES = {
    "B1": [10.727298831515066,106.6967154830272],
    "B2": [10.740600,106.695797],
    "B3": [10.733902,106.708781],
    "B5": [10.73780906347085,106.70517496567874],
    "B6": [10.729986861681768,106.70690372549372],
    "B7": [10.744230207012244,106.6965025304644],
    "B8": [10.741408,106.699883],
    "B9": [10.740970,106.699825],
    "B10": [10.814503,106.670873],
    "B11": [10.77497650247788,106.75134333045331],
    "B12": [10.778874744587053,106.75266727478706],
    "B14": [10.742557513695218,106.69945313180673],
    "B15": [10.775572501574938,106.75167172807936],
    "B16": [10.760347394497392,106.69043939445082],
    "B17": [10.70590976421059, 106.7078826381241],
}

# Map để dịch loại giao dịch Giao Ca sang tiếng Việt
SHIFT_TRANSACTION_TYPES = {
    "BRANCH_ACCOUNT": "Chi nhánh",
    "COMPANY_ACCOUNT": "Công ty",
    "OTA": "OTA",
    "UNC": "UNC",
    "CARD": "Quẹt thẻ",
    "CASH_EXPENSE": "Chi tiền quầy",
}