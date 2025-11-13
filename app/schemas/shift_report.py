# app/schemas/shift_report.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from ..db.models import TransactionType, ShiftReportStatus

# ====================================================================
# SCHEMAS CHO GIAO DỊCH CA (SHIFT REPORT TRANSACTION)
# ====================================================================

# --- Schema cơ bản ---
class ShiftTransactionBase(BaseModel):
    transaction_code: str
    transaction_type: TransactionType
    amount: int
    chi_nhanh: Optional[str] = None

    class Config:
        from_attributes = True # SỬA: Đổi từ orm_mode sang from_attributes cho Pydantic v2

# --- Schema để tạo mới ---
class ShiftTransactionCreate(ShiftTransactionBase):
    room_number: Optional[str] = None
    transaction_info: Optional[str] = None

# --- Schema để cập nhật ---
class ShiftTransactionUpdate(BaseModel):
    transaction_type: Optional[TransactionType] = None
    amount: Optional[int] = None
    chi_nhanh: Optional[str] = None
    recorded_by: Optional[str] = None

# --- Schema chi tiết để hiển thị ---
class ShiftTransactionDetails(ShiftTransactionBase):
    id: int
    status: Optional[str] = None
    transaction_type_display: Optional[str] = None

    created_datetime: Optional[datetime] = None
    closed_datetime: Optional[datetime] = None
    deleted_datetime: Optional[datetime] = None

    recorded_by: Optional[str] = None
    closed_by: Optional[str] = None
    deleted_by: Optional[str] = None
    
    room_number: Optional[str] = None
    transaction_info: Optional[str] = None

# --- Schema cho response API (danh sách) ---
class ShiftTransactionsResponse(BaseModel):
    records: List[ShiftTransactionDetails]
    totalRecords: int
    currentPage: int
    totalPages: int

# --- Schema cho xóa hàng loạt ---
class BatchDeleteTransactionsPayload(BaseModel):
    ids: List[int]

# --- Schema cho kết ca hàng loạt (Admin/Boss) ---
class BatchCloseTransactionsPayload(BaseModel):
    ids: List[int]
    branch: str
    pms_revenue: str