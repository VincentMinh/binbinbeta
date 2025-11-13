# app/services/missing_attendance_service.py
from datetime import datetime, time, timedelta, date
from typing import Optional
from sqlalchemy import and_, or_, cast, Date
from sqlalchemy.orm import Session, joinedload

# Import từ các module đã tái cấu trúc
from ..db.session import SessionLocal
from ..db.models import User, AttendanceRecord, Department
from ..core.config import logger
from ..core.utils import VN_TZ

def run_daily_absence_check(target_date: Optional[date] = None):
    """
    Chạy kiểm tra và ghi nhận nhân viên vắng mặt.
    Nếu target_date được cung cấp, sẽ chạy cho ngày đó (chạy thủ công).
    Nếu không, sẽ chạy cho ngày hôm trước (dùng cho cron job tự động).
    """
    log_prefix = "thủ công"
    if target_date is None:
        target_date = datetime.now(VN_TZ).date() - timedelta(days=1)
        log_prefix = "tự động"

    logger.info(f"Bắt đầu chạy kiểm tra điểm danh vắng {log_prefix} cho ngày {target_date.strftime('%d/%m/%Y')}")
    # Gọi hàm xử lý chính trong cùng file
    update_missing_attendance_to_db(target_date=target_date)
    logger.info(f"Hoàn tất kiểm tra điểm danh vắng cho ngày {target_date.strftime('%d/%m/%Y')}")


def update_missing_attendance_to_db(target_date: Optional[date] = None):
    """
    Kiểm tra và cập nhật các bản ghi vắng mặt cho một ngày cụ thể.
    - Lấy danh sách nhân viên trực tiếp từ bảng users.
    - Hoạt động với kiến trúc database mới.
    """
    if target_date is None:
        workday_to_check = datetime.now().date() - timedelta(days=1)
    else:
        workday_to_check = target_date
    
    workday_str = workday_to_check.strftime('%d/%m/%Y')
    
    with SessionLocal() as db:
        try:
            # 1. Xóa các bản ghi vắng mặt "Hệ thống" cũ cho ngày này để tránh trùng lặp.
            db.query(AttendanceRecord).filter(
                cast(AttendanceRecord.attendance_datetime, Date) == workday_to_check,
                AttendanceRecord.checker_id == None # Giả định checker_id là NULL cho hệ thống
            ).delete(synchronize_session=False)
            db.commit()
            logger.info(f"[ABSENCE_CHECK] Đã xóa các bản ghi vắng mặt cũ cho ngày {workday_str}.")
    
            # 2. Lấy danh sách ID của các nhân viên đã điểm danh trong "ngày làm việc".
            # Ngày làm việc được tính từ 07:00 ngày đó đến 06:59 Sáng hôm sau.
            start_datetime = datetime.combine(workday_to_check, time(7, 0, 0))
            end_datetime = start_datetime + timedelta(days=1)

            checked_in_user_ids = {
                r.user_id for r in db.query(AttendanceRecord.user_id).filter(
                    AttendanceRecord.attendance_datetime >= start_datetime,
                    AttendanceRecord.attendance_datetime < end_datetime,
                    AttendanceRecord.work_units > 0 # Chỉ tính các lần điểm danh có công
                ).distinct().all()
            }
            logger.info(f"[ABSENCE_CHECK] Ngày {workday_str}: Tìm thấy {len(checked_in_user_ids)} nhân viên đã điểm danh.")

            # 3. Lấy danh sách tất cả nhân viên cần điểm danh từ bảng users.
            employees_to_check = db.query(User).options(
                joinedload(User.department),
                joinedload(User.main_branch)
            ).filter(
                User.is_active == True,
                # Loại trừ các vai trò không cần điểm danh
                User.department_id.in_(
                    db.query(Department.id).filter(
                        ~Department.role_code.in_(['boss', 'admin'])
                    )
                )
            ).all()

            # 4. Lọc ra những nhân viên vắng mặt và tạo bản ghi.
            new_absence_records = []
            for emp in employees_to_check:
                if emp.id not in checked_in_user_ids:
                    absence_record = AttendanceRecord(
                        user_id=emp.id,
                        checker_id=None, # NULL để nhận biết là do hệ thống tạo
                        branch_id=emp.main_branch_id,
                        
                        # Dữ liệu snapshot
                        employee_code_snapshot=emp.employee_code,
                        employee_name_snapshot=emp.name,
                        role_snapshot=emp.department.name if emp.department else '',
                        main_branch_snapshot=emp.main_branch.name if emp.main_branch else '',
                        
                        attendance_datetime=datetime.combine(workday_to_check, time(23, 59, 0)),
                        work_units=0.0,
                        is_overtime=False,
                        notes=f"Hệ thống: Vắng mặt ngày {workday_str}"
                    )
                    new_absence_records.append(absence_record)
    
            if not new_absence_records:
                logger.info(f"[ABSENCE_CHECK] Ngày {workday_str}: Không có nhân viên nào vắng mặt.")
                return
    
            # 5. Thêm tất cả các bản ghi vắng mặt vào database.
            db.add_all(new_absence_records)
            db.commit()
            logger.info(f"[ABSENCE_CHECK] Ngày {workday_str}: Đã thêm {len(new_absence_records)} bản ghi vắng mặt.")
    
        except Exception as e:
            logger.error(f"[ABSENCE_CHECK] Lỗi khi cập nhật điểm danh vắng mặt: {e}", exc_info=True)
            db.rollback()
            raise