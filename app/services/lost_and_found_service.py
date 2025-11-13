# app/services/lost_and_found_service.py
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from ..db.models import LostAndFoundItem, LostItemStatus
from ..core.utils import VN_TZ
from ..db.session import SessionLocal
from ..core.config import logger

def update_disposable_items_status(db: Session):
    """
    Cập nhật trạng thái các món đồ từ "Đang lưu giữ"
    sang "Có thể thanh lý" sau 30 ngày.
    Hàm này sử dụng Session được truyền vào để đảm bảo tính nhất quán.
    """
    try:
        # Lấy thời gian hiện tại và trừ đi 30 ngày
        thirty_days_ago = datetime.now(VN_TZ) - timedelta(days=30)
        
        # Thực hiện câu lệnh UPDATE trực tiếp trên DB để tối ưu hiệu suất.
        # Tìm các món đồ có trạng thái "Đang lưu giữ" và ngày phát hiện đã hơn 30 ngày.
        updated_count = db.query(LostAndFoundItem).filter(
            LostAndFoundItem.status == LostItemStatus.STORED,
            LostAndFoundItem.found_datetime < thirty_days_ago
        ).update({"status": LostItemStatus.DISPOSABLE}, synchronize_session=False)
        
        # Không commit ở đây, để cho endpoint tự quản lý commit/rollback

        if updated_count > 0:
            logger.info(f"[STATUS_UPDATE] Đã cập nhật {updated_count} đồ thất lạc sang trạng thái 'Có thể thanh lý'.")

    except Exception as e:
        logger.error(f"[STATUS_UPDATE] Lỗi khi cập nhật trạng thái đồ thất lạc: {e}", exc_info=True)
        # Không rollback ở đây, để endpoint tự quản lý
        raise # Ném lại lỗi để endpoint có thể xử lý
