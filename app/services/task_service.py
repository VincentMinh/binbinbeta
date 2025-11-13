# app/services/task_service.py
from sqlalchemy.orm import Session
from typing import Dict, Optional, Union
from datetime import datetime, timezone

from ..db.models import Task
from ..core.utils import VN_TZ
from ..db.session import SessionLocal
from ..core.config import logger
from sqlalchemy import func

def get_task_stats(db: Session, user_data: dict, branch_id: Optional[int] = None) -> Dict[str, int]:
    """
    Lấy thống kê số lượng công việc theo trạng thái.
    Đã cập nhật để làm việc với kiến trúc mới và sửa lỗi logic filter.
    """
    # Bắt đầu với query cơ bản
    base_query = db.query(Task.status, func.count(Task.id))
    user_role = user_data.get("role")

    # === SỬA LỖI: ÁP DỤNG FILTER TRƯỚC KHI GROUP BY ===
    # Áp dụng bộ lọc theo vai trò và chi nhánh vào query cơ bản
    if user_role == "letan" and branch_id:
        base_query = base_query.filter(
            Task.branch_id == branch_id,
            Task.status != "Đã xoá"
        )
    elif user_role == "ktv":
        base_query = base_query.filter(Task.status != "Đã xoá")
    
    # Thực thi query đã được lọc
    counts = base_query.group_by(Task.status).all()

    # Phần xử lý kết quả giữ nguyên
    stats = {"total": 0, "pending": 0, "completed": 0, "overdue": 0, "deleted": 0}
    status_map = {
        "Đang chờ": "pending",
        "Hoàn thành": "completed",
        "Quá hạn": "overdue",
        "Đã xoá": "deleted"
    }

    for status, count in counts:
        key = status_map.get(status)
        if key:
            stats[key] = count
        # Chỉ tính total cho các trạng thái không bị ẩn
        if user_role not in ["quanly", "admin", "boss"] and status == "Đã xoá":
            continue
        stats["total"] += count
        
    return stats


def is_overdue(task: Task) -> bool:
    """
    Kiểm tra xem công việc có quá hạn không.
    """
    if task.status in ["Hoàn thành", "Đã xoá"]:
        return False
    if not task.due_date:
        return False

    now_aware = datetime.now(VN_TZ)
    
    due_date_aware = task.due_date
    if due_date_aware.tzinfo is None:
        # === CẢI THIỆN: An toàn hơn khi giả định giờ trong DB là UTC ===
        due_date_aware = due_date_aware.replace(tzinfo=timezone.utc).astimezone(VN_TZ)

    return due_date_aware < now_aware

def update_overdue_tasks_status():
    """
    Tác vụ nền tự động cập nhật trạng thái các công việc từ "Đang chờ" sang "Quá hạn".
    Hàm này tự quản lý session DB để có thể chạy độc lập trong một tiến trình nền (background job).
    """
    with SessionLocal() as db:
        try:
            # Lấy thời gian hiện tại theo múi giờ Việt Nam
            now_vn = datetime.now(VN_TZ)
            
            # Thực hiện một câu lệnh UPDATE trực tiếp trên DB để tối ưu hiệu suất.
            # So sánh thời gian đầy đủ của due_date với thời gian hiện tại.
            # Một công việc được coi là quá hạn nếu thời gian hiện tại đã vượt qua hạn hoàn thành.
            updated_count = db.query(Task).filter(
                Task.status == "Đang chờ",
                Task.due_date < now_vn
            ).update({"status": "Quá hạn"}, synchronize_session=False)
            
            db.commit()

            if updated_count > 0:
                logger.info(f"[AUTO_UPDATE_STATUS] Đã cập nhật {updated_count} công việc sang trạng thái 'Quá hạn'.")
            else:
                # Log ở mức DEBUG để tránh làm nhiễu log khi không có gì thay đổi
                logger.debug("[AUTO_UPDATE_STATUS] Không có công việc nào cần cập nhật trạng thái.")

        except Exception as e:
            logger.error(f"[AUTO_UPDATE_STATUS] Lỗi khi cập nhật trạng thái công việc quá hạn: {e}", exc_info=True)
            db.rollback()