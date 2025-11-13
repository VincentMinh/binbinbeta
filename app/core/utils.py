from datetime import datetime, timedelta
from pytz import timezone
from typing import Optional
from urllib.parse import parse_qsl, urlencode
import socket

# --- CÁC HẰNG SỐ CỦA ỨNG DỤNG ---
VN_TZ = timezone("Asia/Ho_Chi_Minh")

def get_lan_ip() -> str:
    """Lấy địa chỉ IP nội bộ (LAN) của máy chủ."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Không cần phải kết nối được, chỉ là một mẹo để lấy IP
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'  # Fallback nếu không lấy được IP
    finally:
        s.close()
    return IP

def get_current_work_shift():
    """
    Xác định ngày làm việc và ca làm việc hiện tại dựa trên giờ Việt Nam.
    Ngày làm việc bắt đầu từ 7h sáng.
    """
    now_vn = datetime.now(VN_TZ)
    work_date = now_vn.date()
    
    if now_vn.hour < 7:
        work_date -= timedelta(days=1)

    if 7 <= now_vn.hour < 19:
        shift_name = "Ca ngày"
    else:
        shift_name = "Ca đêm"
        
    return work_date, shift_name

def _get_log_shift_for_user(role: str, shift_name: str) -> str:
    """Xác định giá trị 'shift' để ghi vào log dựa trên vai trò và ca."""
    return "Ca đêm" if role == "buongphong" else shift_name

def parse_datetime_input(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Chuyển đổi chuỗi ngày tháng (có thể có hoặc không có giờ) thành đối tượng datetime có timezone.
    Hỗ trợ các định dạng phổ biến như 'YYYY-MM-DD' và 'YYYY-MM-DDTHH:MM'.
    """
    if not dt_str:
        return None
    try:
        # Thử định dạng có cả giờ và phút
        dt_obj = datetime.strptime(dt_str, "%Y-%m-%dT%H:%M")
    except ValueError:
        try:
            # Thử định dạng chỉ có ngày
            dt_obj = datetime.strptime(dt_str, "%Y-%m-%d")
        except ValueError:
            return None  # Trả về None nếu không khớp định dạng nào
    return VN_TZ.localize(dt_obj)

def parse_form_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Chuyển đổi chuỗi ngày tháng từ form (dd/mm/yyyy HH:MM) thành đối tượng datetime có timezone.
    """
    if not dt_str:
        return None
    try:
        # 1. Tạo datetime "ngây thơ" (naive) từ chuỗi nhập vào.
        naive_dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M")
        # 2. Gán múi giờ Việt Nam cho nó.
        local_dt = VN_TZ.localize(naive_dt)
        # 3. Chuyển đổi nó về múi giờ UTC để lưu trữ.
        return local_dt.astimezone(timezone('UTC'))
    except ValueError:
        return None

def format_datetime_display(dt: Optional[datetime], with_time: bool = False) -> str:
    """
    Hàm định dạng datetime để hiển thị, luôn đảm bảo chuyển đổi đúng sang múi giờ Việt Nam.
    """
    if not dt:
        return ""

    # Luôn chuyển đổi datetime về múi giờ Việt Nam trước khi định dạng
    # Nếu datetime đã có timezone (aware), astimezone() sẽ chuyển đổi nó.
    # Nếu datetime không có timezone (naive), ta giả định nó là giờ UTC và chuyển đổi.
    if dt.tzinfo is None:
        # Giả định thời gian lưu trong DB là UTC nếu nó không có thông tin timezone
        dt_local = dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(VN_TZ)
    else:
        # Nếu đã có thông tin timezone, chỉ cần chuyển đổi nó
        dt_local = dt.astimezone(VN_TZ)

    if with_time:
        # Định dạng có cả ngày và giờ (ví dụ: 20/10/2025 23:48)
        return dt_local.strftime("%d/%m/%Y %H:%M")
    
    # Chỉ định dạng ngày (ví dụ: 20/10/2025)
    return dt_local.strftime("%d/%m/%Y")

def clean_query_string(query_string: str, keys_to_remove: list = None) -> str:
    """
    Xóa các tham số không mong muốn khỏi query string để tạo URL redirect sạch.
    """
    if keys_to_remove is None:
        keys_to_remove = ["success", "action", "json"]
    
    query_params = parse_qsl(query_string)
    filtered_params = [(k, v) for k, v in query_params if k not in keys_to_remove]
    
    return urlencode(filtered_params)