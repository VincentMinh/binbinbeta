# app/schemas/lost_and_found.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

# ====================================================================
# SCHEMAS DÙNG CHO REQUEST BODY (Dữ liệu API nhận vào)
# ====================================================================

class LostItemCreate(BaseModel):
    """Schema để xác thực dữ liệu khi thêm mới một món đồ."""
    item_name: str
    description: Optional[str] = None
    found_location: str
    chi_nhanh: str  # Frontend sẽ gửi branch_code
    reported_by: str # Frontend sẽ gửi employee_code
    
    # Các trường tùy chọn
    owner_name: Optional[str] = None
    owner_contact: Optional[str] = None
    notes: Optional[str] = None
    
    # Admin/Boss có thể ghi nhận cho người khác
    recorded_by: Optional[str] = None # employee_code

class LostItemUpdate(BaseModel):
    """Schema để xác thực dữ liệu khi cập nhật trạng thái."""
    action: str  # 'return' hoặc 'dispose'
    owner_name: Optional[str] = None
    owner_contact: Optional[str] = None
    disposed_by: Optional[str] = None # employee_code
    disposed_amount: Optional[float] = None
    notes: Optional[str] = None

class BatchDeleteLostItemsPayload(BaseModel):
    """Schema cho việc xóa hàng loạt."""
    ids: List[int]

# ====================================================================
# SCHEMAS DÙNG CHO RESPONSE (Dữ liệu API trả về)
# ====================================================================

class LostItemBase(BaseModel):
    """Các trường thông tin cơ bản của một món đồ thất lạc."""
    id: int
    item_name: str
    status: str # Sẽ là giá trị đã được dịch sang tiếng Việt
    chi_nhanh: Optional[str] = None

    class Config:
        from_attributes = True

class LostItemDetails(BaseModel):
    id: int
    item_name: str
    description: Optional[str] = None
    found_location: Optional[str] = None
    found_datetime: datetime
    status: str # Sẽ được map sang tiếng Việt
    owner_name: Optional[str] = None
    owner_contact: Optional[str] = None

    receiver_name: Optional[str] = None
    receiver_contact: Optional[str] = None
    update_notes: Optional[str] = None
    
    # THÊM DÒNG NÀY VÀO SCHEMA CỦA BẠN
    return_date: Optional[datetime] = None  # <--- THÊM VÀO ĐÂY

    disposed_amount: Optional[float] = None # Dùng float để khớp với NUMERIC
    notes: Optional[str] = None
    deleted_datetime: Optional[datetime] = None # Thêm cả trường này cho logic xóa
    
    # Các trường sẽ được điền thủ công trong API
    chi_nhanh: Optional[str] = None
    reported_by: Optional[str] = None
    recorded_by: Optional[str] = None
    disposed_by: Optional[str] = None
    deleted_by: Optional[str] = None

    class Config:
        from_attributes = True # SỬA: Đổi từ orm_mode sang from_attributes cho Pydantic v2

class LostItemsResponse(BaseModel):
    """Schema cho toàn bộ phản hồi của API /api/lost-and-found."""
    records: List[LostItemDetails]
    currentPage: int
    totalPages: int
    totalRecords: int