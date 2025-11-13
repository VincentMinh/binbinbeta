from sqlalchemy.orm import Session
from ..db.models import User, Branch, Department
from ..core.config import logger

def sync_employees_from_source(db: Session, employees_source: list[dict], force_delete: bool = False):
    """
    Đồng bộ nhân viên từ file nguồn vào DB theo kiến trúc mới.
    - Sử dụng employee_id làm khóa chính.
    - Liên kết với bảng branches và departments.
    """
    logger.info("[SYNC] Bắt đầu quá trình đồng bộ nhân viên...")

    # 1. Nạp dữ liệu gốc (branches, departments) vào cache để truy vấn nhanh
    branch_map = {b.branch_code: b.id for b in db.query(Branch).all()}
    department_map = {d.role_code: d.id for d in db.query(Department).all()}
    logger.info(f"[SYNC] Đã nạp {len(branch_map)} chi nhánh và {len(department_map)} phòng ban.")

    # 2. Lấy danh sách nhân viên hiện có trong DB
    existing_users_dict = {user.employee_id: user for user in db.query(User).all()}
    source_ids = {emp.get("employee_id", "").strip() for emp in employees_source if emp.get("employee_id")}

    # 3. Xóa các nhân viên không còn trong file nguồn (nếu cần)
    if force_delete:
        ids_to_delete = set(existing_users_dict.keys()) - source_ids
        if ids_to_delete:
            db.query(User).filter(User.employee_id.in_(ids_to_delete)).delete(synchronize_session=False)
            logger.info(f"[SYNC] Đã xóa {len(ids_to_delete)} nhân viên: {', '.join(ids_to_delete)}")

    # 4. Thêm mới hoặc cập nhật nhân viên
    updated_count = 0
    for emp in employees_source:
        employee_id = emp.get("employee_id", "").strip()
        if not employee_id:
            continue

        # Lấy thông tin từ file và kiểm tra với dữ liệu gốc
        branch_code = emp.get("branch")
        role_code = emp.get("role")
        
        branch_id = branch_map.get(branch_code)
        department_id = department_map.get(role_code)

        if not branch_id:
            logger.warning(f"[SYNC] Bỏ qua nhân viên '{emp.get('name')}' vì branch_code '{branch_code}' không tồn tại trong bảng branches.")
            continue
        if not department_id:
            logger.warning(f"[SYNC] Bỏ qua nhân viên '{emp.get('name')}' vì role_code '{role_code}' không tồn tại trong bảng departments.")
            continue

        existing_user = existing_users_dict.get(employee_id)
        
        if existing_user:
            # Cập nhật nhân viên đã có
            # Kiểm tra xem có sự thay đổi nào không trước khi cập nhật
            changed = False
            if existing_user.employee_code != emp.get("code"): existing_user.employee_code = emp.get("code"); changed = True
            if existing_user.name != emp.get("name"): existing_user.name = emp.get("name"); changed = True
            if existing_user.main_branch_id != branch_id: existing_user.main_branch_id = branch_id; changed = True
            if existing_user.department_id != department_id: existing_user.department_id = department_id; changed = True
            if existing_user.shift != emp.get("shift"): existing_user.shift = emp.get("shift"); changed = True
            
            # Chỉ cập nhật mật khẩu nếu có mật khẩu mới trong file nguồn
            new_password = emp.get("password")
            if new_password and existing_user.password != new_password:
                existing_user.password = new_password
                changed = True
            
            if changed:
                updated_count += 1
                logger.debug(f"[SYNC] Cập nhật thông tin cho: {employee_id} - {emp.get('name')}")
        else:
            # Thêm nhân viên mới
            new_user = User(
                employee_id=employee_id,
                employee_code=emp.get("code"),
                name=emp.get("name"),
                password=emp.get("password", "999"), # Mật khẩu mặc định
                main_branch_id=branch_id,
                department_id=department_id,
                shift=emp.get("shift")
            )
            db.add(new_user)
            logger.info(f"[SYNC] Thêm nhân viên mới: {employee_id} - {emp.get('name')}")

    if updated_count > 0:
        logger.info(f"[SYNC] Đã cập nhật thông tin cho {updated_count} nhân viên.")

    db.commit()
    logger.info("[SYNC] Hoàn tất đồng bộ nhân viên.")