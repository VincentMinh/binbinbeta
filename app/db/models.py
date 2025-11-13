# models.py
import enum
from sqlalchemy import (
    Column, String, Integer, DateTime, Text, Date, Boolean, Float, Time,
    Enum as SQLAlchemyEnum, ForeignKey, BIGINT, NUMERIC, Index
)
from sqlalchemy.dialects.postgresql import JSON
from datetime import datetime
from ..core.utils import VN_TZ
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from .session import Base

# ====================================================================
# BẢNG DỮ LIỆU GỐC (MASTER DATA)
# ====================================================================

class Branch(Base):
    """Bảng quản lý danh sách các chi nhánh."""
    __tablename__ = "branches"
    
    id = Column(Integer, primary_key=True)
    branch_code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(Text)
    gps_lat = Column(NUMERIC(12, 9))
    gps_lng = Column(NUMERIC(12, 9))
    created_at = Column(DateTime(timezone=True))

class Department(Base):
    """Bảng quản lý danh sách các phòng ban, vai trò."""
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True)
    role_code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)

# ====================================================================
# BẢNG NGƯỜI DÙNG (USERS)
# ====================================================================

class User(Base): # type: ignore
    __tablename__ = "users"
    
    id = Column(BIGINT, primary_key=True)
    employee_id = Column(String(50), unique=True, nullable=False, index=True)
    employee_code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    password = Column(String(255), nullable=True)
    
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"))
    main_branch_id = Column(Integer, ForeignKey("branches.id", ondelete="SET NULL"))
    
    shift = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True))
    phone_number = Column(String(20))
    email = Column(String(255))
    last_active_branch = Column(String, nullable=True)

    # ORM Relationships
    department = relationship("Department")
    main_branch = relationship("Branch")
    
    # === CÁC MỐI QUAN HỆ HAI CHIỀU ĐÃ HOÀN CHỈNH ===

    # -- Attendance --
    attendance_logs = relationship("AttendanceLog", back_populates="user")
    attendance_records_as_subject = relationship(
        "AttendanceRecord", 
        foreign_keys="[AttendanceRecord.user_id]", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    attendance_records_as_checker = relationship(
        "AttendanceRecord", 
        foreign_keys="[AttendanceRecord.checker_id]",
        back_populates="checker"
    )

    # -- Service --
    service_records_as_subject = relationship(
        "ServiceRecord",
        foreign_keys="[ServiceRecord.user_id]",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    service_records_as_checker = relationship(
        "ServiceRecord",
        foreign_keys="[ServiceRecord.checker_id]",
        back_populates="checker"
    )

    # -- Tasks --
    created_tasks = relationship("Task", foreign_keys="[Task.author_id]", back_populates="author")
    assigned_tasks = relationship("Task", foreign_keys="[Task.assignee_id]", back_populates="assignee")
    deleted_tasks = relationship("Task", foreign_keys="[Task.deleter_id]", back_populates="deleter")

    # -- Lost & Found --
    reported_lost_items = relationship("LostAndFoundItem", foreign_keys="[LostAndFoundItem.reporter_id]", back_populates="reporter")
    recorded_lost_items = relationship("LostAndFoundItem", foreign_keys="[LostAndFoundItem.recorder_id]", back_populates="recorder")
    disposed_lost_items = relationship("LostAndFoundItem", foreign_keys="[LostAndFoundItem.disposer_id]", back_populates="disposer")
    deleted_lost_items = relationship("LostAndFoundItem", foreign_keys="[LostAndFoundItem.deleter_id]", back_populates="deleter")

    # === MỚI: MỐI QUAN HỆ GIAO CA ===
    recorded_shift_transactions = relationship("ShiftReportTransaction", foreign_keys="[ShiftReportTransaction.recorder_id]", back_populates="recorder")
    closed_shift_transactions = relationship("ShiftReportTransaction", foreign_keys="[ShiftReportTransaction.closer_id]", back_populates="closer")
    deleted_shift_transactions = relationship("ShiftReportTransaction", foreign_keys="[ShiftReportTransaction.deleter_id]", back_populates="deleter")

    # === MỚI: MỐI QUAN HỆ LỊCH SỬ KẾT CA ===
    shift_close_logs = relationship("ShiftCloseLog", back_populates="closer")


# ====================================================================
# BẢNG GIAO DỊCH (TRANSACTIONAL TABLES)
# ====================================================================

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(BIGINT, primary_key=True)
    id_task = Column(String, unique=True, index=True, nullable=False)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    author_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    assignee_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    deleter_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    
    room_number = Column(String(50))
    description = Column(Text, nullable=False)
    department = Column(String(100), nullable=True)
    status = Column(String(50), default='Đang chờ', index=True)
    due_date = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True))
    deleted_at = Column(DateTime(timezone=True))

    # ORM Relationships
    branch = relationship("Branch")
    author = relationship("User", foreign_keys=[author_id], back_populates="created_tasks")
    assignee = relationship("User", foreign_keys=[assignee_id], back_populates="assigned_tasks")
    deleter = relationship("User", foreign_keys=[deleter_id], back_populates="deleted_tasks")

class AttendanceLog(Base):
    __tablename__ = "attendance_log"
    
    id = Column(BIGINT, primary_key=True)
    user_id = Column(BIGINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    shift = Column(String(10))
    token = Column(String(255), unique=True)
    checked_in = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="attendance_logs")

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    
    id = Column(BIGINT, primary_key=True)
    user_id = Column(BIGINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    checker_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    employee_code_snapshot = Column(String(50))
    employee_name_snapshot = Column(String(100))
    role_snapshot = Column(String(50))
    main_branch_snapshot = Column(String(50))
    
    attendance_datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    work_units = Column(Float, default=1.0)
    is_overtime = Column(Boolean, default=False)
    notes = Column(Text)

    user = relationship("User", back_populates="attendance_records_as_subject", foreign_keys=[user_id])
    checker = relationship("User", back_populates="attendance_records_as_checker", foreign_keys=[checker_id])
    branch = relationship("Branch")

class ServiceRecord(Base):
    __tablename__ = "service_records"
    
    id = Column(BIGINT, primary_key=True)
    user_id = Column(BIGINT, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    checker_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    
    employee_code_snapshot = Column(String(50))
    employee_name_snapshot = Column(String(100))
    role_snapshot = Column(String(50))
    main_branch_snapshot = Column(String(50))
    
    service_datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    service_type = Column(String(100))
    room_number = Column(String(50))
    quantity = Column(Integer)
    is_overtime = Column(Boolean, default=False)
    notes = Column(Text)
    
    user = relationship("User", back_populates="service_records_as_subject", foreign_keys=[user_id])
    checker = relationship("User", back_populates="service_records_as_checker", foreign_keys=[checker_id])
    branch = relationship("Branch")

# ====================================================================
# BẢNG ĐỒ THẤT LẠC (LOST & FOUND)
# ====================================================================

class LostItemStatus(str, enum.Enum):
    STORED = "STORED"       
    RETURNED = "RETURNED"
    DISPOSED = "DISPOSED"
    DISPOSABLE = "DISPOSABLE"
    DELETED = "DELETED"

class LostAndFoundItem(Base):
    __tablename__ = "lost_and_found_items"
    
    id = Column(BIGINT, primary_key=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    reporter_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    recorder_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    
    item_name = Column(String(255), nullable=False)
    description = Column(Text)
    found_location = Column(String(255))
    found_datetime = Column(DateTime(timezone=True), nullable=False)
    status = Column(SQLAlchemyEnum(LostItemStatus, name="lostitemstatus", native_enum=True), default=LostItemStatus.STORED, index=True)
    
    owner_name = Column(String(100))
    owner_contact = Column(String(100))
    return_datetime = Column(DateTime(timezone=True))

    receiver_name = Column(String, nullable=True)
    receiver_contact = Column(String, nullable=True)
    update_notes = Column(Text, nullable=True)
    
    disposer_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"))
    disposed_amount = Column(NUMERIC(12, 2))
    
    deleter_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"))
    deleted_datetime = Column(DateTime(timezone=True))
    notes = Column(Text)
    
    # --- CỘT CHO FULL-TEXT SEARCH ---
    fts_vector = Column(TSVECTOR, index=True)

    branch = relationship("Branch")
    reporter = relationship("User", foreign_keys=[reporter_id], back_populates="reported_lost_items")
    recorder = relationship("User", foreign_keys=[recorder_id], back_populates="recorded_lost_items")
    disposer = relationship("User", foreign_keys=[disposer_id], back_populates="disposed_lost_items")
    deleter = relationship("User", foreign_keys=[deleter_id], back_populates="deleted_lost_items")

# ====================================================================
# BẢNG GIAO DỊCH CA (SHIFT REPORT)
# ====================================================================

class ShiftReportStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLOSED = "CLOSED"
    DELETED = "DELETED"

class TransactionType(str, enum.Enum):
    CARD = "CARD"
    UNC = "UNC"
    OTA = "OTA"
    COMPANY_ACCOUNT = "COMPANY_ACCOUNT"
    BRANCH_ACCOUNT = "BRANCH_ACCOUNT"
    CASH_EXPENSE = "CASH_EXPENSE"

class ShiftReportTransaction(Base):
    __tablename__ = "shift_report_transactions"
    
    id = Column(BIGINT, primary_key=True)
    transaction_code = Column(String(50), unique=True, nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id", ondelete="RESTRICT"), nullable=False, index=True)
    recorder_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    
    transaction_type = Column(SQLAlchemyEnum(TransactionType, name="transactiontype", native_enum=True), nullable=False, index=True)
    amount = Column(BIGINT, nullable=False, index=True) # Dùng BIGINT cho tiền VNĐ
    room_number = Column(String(50), nullable=True, index=True) # THÊM: Số phòng
    transaction_info = Column(String(255), nullable=True) # THÊM: Thông tin giao dịch (VD: mã booking, tên khách)
    status = Column(SQLAlchemyEnum(ShiftReportStatus, name="shiftreportstatus", native_enum=True), default=ShiftReportStatus.PENDING, index=True)
    
    created_datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    
    closer_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    closed_datetime = Column(DateTime(timezone=True))
    
    deleter_id = Column(BIGINT, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    deleted_datetime = Column(DateTime(timezone=True))

    # --- CỘT CHO FULL-TEXT SEARCH ---
    fts_vector = Column(TSVECTOR, index=True)

    # ORM Relationships
    branch = relationship("Branch")
    recorder = relationship("User", foreign_keys=[recorder_id], back_populates="recorded_shift_transactions")
    closer = relationship("User", foreign_keys=[closer_id], back_populates="closed_shift_transactions")
    deleter = relationship("User", foreign_keys=[deleter_id], back_populates="deleted_shift_transactions")

# ====================================================================
# BẢNG GHI NHẬN LỊCH SỬ KẾT CA (SHIFT CLOSE LOG)
# ====================================================================
class ShiftCloseLog(Base):
    __tablename__ = 'shift_close_logs'

    id = Column(Integer, primary_key=True, index=True)
    
    branch_id = Column(Integer, ForeignKey('branches.id'), nullable=False)
    branch = relationship("Branch")

    closer_id = Column(BIGINT, ForeignKey('users.id'), nullable=False)
    closer = relationship("User", back_populates="shift_close_logs")

    closed_datetime = Column(DateTime(timezone=True), default=lambda: datetime.now(VN_TZ), nullable=False)
    
    pms_revenue = Column(BIGINT, nullable=False, default=0)
    closed_online_revenue = Column(BIGINT, nullable=False, default=0)
    closed_branch_revenue = Column(BIGINT, nullable=False, default=0)
    closed_transaction_ids = Column(JSON, nullable=True) # Lưu danh sách ID các giao dịch đã kết trong lần này