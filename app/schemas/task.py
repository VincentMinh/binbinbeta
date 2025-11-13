from pydantic import BaseModel, computed_field
from typing import Optional, Any
from datetime import datetime
 
# === ĐỊNH NGHĨA CÁC SCHEMA PHỤ ĐỂ SERIALIZE ===
# Các schema này chỉ cần chứa các trường mà bạn muốn trả về trong API.
# `from_attributes = True` là bắt buộc để Pydantic có thể đọc từ đối tượng SQLAlchemy.
 
class UserForTask(BaseModel):
    id: int
    name: str
 
    class Config:
        from_attributes = True # SỬA: Đổi từ orm_mode sang from_attributes cho Pydantic v2
 
class BranchForTask(BaseModel):
    id: int
    name: str # Giả định model Branch có thuộc tính `name`
    branch_code: str
 
    class Config:
        from_attributes = True # SỬA: Đổi từ orm_mode sang from_attributes cho Pydantic v2
 
class TaskBase(BaseModel):
    room_number: Optional[str]
    description: str
    notes: Optional[str]
    due_date: Optional[datetime]
    status: Optional[str]

class TaskCreate(TaskBase):
    branch_id: int

class TaskUpdate(TaskBase):
    pass

class TaskInDB(TaskBase):
    id: int
    author_id: int
    branch_id: int
    created_at: datetime
    author: Optional[UserForTask] = None
    assignee: Optional[UserForTask] = None
    branch: Optional[BranchForTask] = None

    class Config:
        from_attributes = True # SỬA: Đổi từ orm_mode sang from_attributes cho Pydantic v2

class Task(TaskInDB):
    pass