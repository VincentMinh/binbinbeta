from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import cast, Date, select, literal_column, union_all, desc, asc, or_, and_, func, Integer, Float, case
from sqlalchemy.orm import aliased
import os
from typing import Optional, Tuple, List, Dict
import math
from datetime import datetime

from ..db.session import get_db
from ..db.models import AttendanceRecord, ServiceRecord, User, Branch
from ..core.security import require_checked_in_user
from ..core.config import ROLE_MAP, BRANCHES, logger
from fastapi.encoders import jsonable_encoder
from ..core.utils import parse_form_datetime, format_datetime_display

from fastapi.templating import Jinja2Templates

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục gốc của project 'app'
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tạo đường dẫn tuyệt đối đến thư mục templates
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

def _get_filtered_records_query(db: Session, query_params: dict, user_session: dict) -> Tuple[select, List]:
    """
    Hàm helper để xây dựng câu query lọc kết quả điểm danh, có thể tái sử dụng.
    Trả về một tuple: (câu query, danh sách các cột đã chọn).
    """
    if not user_session:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập chức năng này.")

    user_id = user_session.get("id")
    user_role = user_session.get("role")

    # Tạo alias để phân biệt User (người được điểm danh) và Checker (người điểm danh)
    # Các cột được chọn ở đây sẽ quyết định những gì được xuất ra file Excel.
    # Tên cột (label) nên thân thiện với người dùng.
    UserEmployee = aliased(User, name="user_employee")
    CheckerEmployee = aliased(User, name="checker_employee")

    # --- Query cho AttendanceRecord ---
    att_q = select(
        AttendanceRecord.id,
        literal_column("'Điểm danh'").label("type"),
        AttendanceRecord.attendance_datetime.label("ThoiGian"),
        func.coalesce(CheckerEmployee.employee_code, 'Hệ thống').label("MaNguoiThucHien"),
        func.coalesce(CheckerEmployee.name, 'Hệ thống').label("TenNguoiThucHien"),
        AttendanceRecord.employee_code_snapshot.label("MaNV"),
        AttendanceRecord.employee_name_snapshot.label("TenNV"),
        AttendanceRecord.role_snapshot.label("ChucVu"),
        AttendanceRecord.main_branch_snapshot.label("ChiNhanhChinh"),
        Branch.branch_code.label("ChiNhanhLam"),
        AttendanceRecord.work_units.label("SoCong"),
        AttendanceRecord.is_overtime.label("TangCa"),
        AttendanceRecord.notes.label("GhiChu"),
        literal_column("''").label("DichVu"),
        literal_column("''").label("SoPhong"),
        literal_column("NULL").cast(Integer).label("SoLuong")
    ).select_from(AttendanceRecord
    ).join(Branch, AttendanceRecord.branch_id == Branch.id
    ).outerjoin(UserEmployee, AttendanceRecord.user_id == UserEmployee.id
    ).outerjoin(CheckerEmployee, AttendanceRecord.checker_id == CheckerEmployee.id)

    # --- Query cho ServiceRecord ---
    svc_q = select(
        ServiceRecord.id,
        literal_column("'Dịch vụ'").label("type"),
        ServiceRecord.service_datetime.label("ThoiGian"),
        func.coalesce(CheckerEmployee.employee_code, 'Hệ thống').label("MaNguoiThucHien"),
        func.coalesce(CheckerEmployee.name, 'Hệ thống').label("TenNguoiThucHien"),
        ServiceRecord.employee_code_snapshot.label("MaNV"),
        ServiceRecord.employee_name_snapshot.label("TenNV"),
        ServiceRecord.role_snapshot.label("ChucVu"),
        ServiceRecord.main_branch_snapshot.label("ChiNhanhChinh"),
        Branch.branch_code.label("ChiNhanhLam"),
        literal_column("NULL").cast(Float).label("SoCong"),
        ServiceRecord.is_overtime.label("TangCa"),
        ServiceRecord.notes.label("GhiChu"),
        ServiceRecord.service_type.label("DichVu"),
        ServiceRecord.room_number.label("SoPhong"),
        ServiceRecord.quantity.label("SoLuong")
    ).select_from(ServiceRecord
    ).join(Branch, ServiceRecord.branch_id == Branch.id
    ).outerjoin(UserEmployee, ServiceRecord.user_id == UserEmployee.id
    ).outerjoin(CheckerEmployee, ServiceRecord.checker_id == CheckerEmployee.id)

    # Lọc theo vai trò người dùng
    if user_role not in ["admin", "boss"]:
        att_q = att_q.where(or_(AttendanceRecord.checker_id == user_id, AttendanceRecord.user_id == user_id))
        svc_q = svc_q.where(or_(ServiceRecord.checker_id == user_id, ServiceRecord.user_id == user_id))

    # Gộp 2 query
    u = union_all(att_q, svc_q).alias("u")
    final_query = select(u)
    selected_columns = u.c # Giữ lại danh sách các cột đã chọn

    # --- Áp dụng các bộ lọc ---
    filter_type = query_params.get("filter_type")
    filter_date = query_params.get("filter_date")
    filter_nhan_vien = query_params.get("filter_nhan_vien")
    filter_chuc_vu = query_params.get("filter_chuc_vu")
    filter_cn_lam = query_params.get("filter_cn_lam")
    filter_ghi_chu = query_params.get("filter_ghi_chu")
    filter_dich_vu = query_params.get("filter_dich_vu")
    filter_so_phong = query_params.get("filter_so_phong")
    filter_nguoi_thuc_hien = query_params.get("filter_nguoi_thuc_hien")
    filter_tang_ca = query_params.get("filter_tang_ca")
    filter_so_cong_str = query_params.get("filter_so_cong")

    if filter_type: final_query = final_query.where(u.c.type == filter_type)
    if filter_date:
        try:
            parsed_date = datetime.strptime(filter_date, "%Y-%m-%d").date()
            final_query = final_query.where(cast(u.c.ThoiGian, Date) == parsed_date)
        except ValueError: pass
    if filter_nhan_vien: final_query = final_query.where(or_(u.c.MaNV.ilike(f"%{filter_nhan_vien}%"), u.c.TenNV.ilike(f"%{filter_nhan_vien}%")))
    if filter_chuc_vu: final_query = final_query.where(u.c.ChucVu.ilike(f"%{filter_chuc_vu}%"))
    if filter_cn_lam: final_query = final_query.where(u.c.ChiNhanhLam == filter_cn_lam)
    if filter_ghi_chu: final_query = final_query.where(u.c.GhiChu.ilike(f"%{filter_ghi_chu}%"))
    if filter_dich_vu: final_query = final_query.where(u.c.DichVu.ilike(f"%{filter_dich_vu}%"))
    if filter_so_phong: final_query = final_query.where(u.c.SoPhong.ilike(f"%{filter_so_phong}%"))
    if filter_nguoi_thuc_hien and user_role in ['admin', 'boss']: final_query = final_query.where(or_(u.c.MaNguoiThucHien.ilike(f"%{filter_nguoi_thuc_hien}%"), u.c.TenNguoiThucHien.ilike(f"%{filter_nguoi_thuc_hien}%")))
    if filter_tang_ca and filter_tang_ca != 'all': final_query = final_query.where(u.c.TangCa == (filter_tang_ca == 'yes'))
    if filter_so_cong_str is not None:
        try:
            filter_so_cong = float(filter_so_cong_str)
            final_query = final_query.where(u.c.SoCong == filter_so_cong)
        except (ValueError, TypeError):
            pass

    return final_query, selected_columns

@router.get("/api/results-by-checker")
async def api_get_attendance_results(request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập chức năng này.")

    query_params = request.query_params
    page = int(query_params.get("page", 1))
    per_page = int(query_params.get("per_page", 100))
    sort_by_map = {
        'thoi_gian': 'ThoiGian', 'nguoi_thuc_hien': 'MaNguoiThucHien', 'ma_nv': 'MaNV',
        'ten_nv': 'TenNV', 'chuc_vu': 'ChucVu', 'chi_nhanh_lam': 'ChiNhanhLam',
        'la_tang_ca': 'TangCa', 'so_cong': 'SoCong', 'dich_vu': 'DichVu',
        'so_phong': 'SoPhong', 'so_luong': 'SoLuong', 'type': 'type'
    }
    sort_by_key = query_params.get("sort_by", 'thoi_gian')
    sort_by = sort_by_map.get(sort_by_key, 'ThoiGian')
    sort_order = query_params.get("sort_order", 'desc')

    # --- TỐI ƯU HÓA HIỆU SUẤT ---
    # Tách truy vấn lấy dữ liệu và truy vấn thống kê thành 2 truy vấn riêng biệt.
    # Việc sử dụng window function (OVER()) để lấy tổng số trên mỗi dòng là rất chậm.

    # 1. Lấy câu query cơ sở đã được lọc
    base_filtered_query, _ = _get_filtered_records_query(db, query_params, user_session)
    
    # 2. Tạo truy vấn thống kê (không sắp xếp, không phân trang)
    stats_subquery = base_filtered_query.subquery('stats_sq')
    stats_query = select(
        func.count().label("total_records"),
        func.sum(case((stats_subquery.c.type == 'Điểm danh', stats_subquery.c.SoCong), else_=0)).label("total_work_units"),
        func.count(case((stats_subquery.c.TangCa == True, 1), else_=None)).label("total_overtime"),
        func.sum(case((stats_subquery.c.type == 'Dịch vụ', stats_subquery.c.SoLuong), else_=0)).label("total_services"),
        func.count(case((and_(stats_subquery.c.type == 'Điểm danh', stats_subquery.c.SoCong == 0), 1), else_=None)).label("total_absences")
    )
    # Thực thi truy vấn thống kê
    stats_result = db.execute(stats_query).first()

    # 3. Tạo và thực thi truy vấn lấy dữ liệu đã phân trang
    data_subquery = base_filtered_query.subquery('data_sq')
    sort_column = getattr(data_subquery.c, sort_by, data_subquery.c.ThoiGian)
    sort_direction = desc if sort_order == 'desc' else asc
    paginated_query = select(data_subquery).order_by(sort_direction(sort_column)).offset((page - 1) * per_page).limit(per_page)
    records = db.execute(paginated_query).all()

    # 4. Xử lý kết quả
    total_records = stats_result.total_records if stats_result else 0
    total_pages = math.ceil(total_records / per_page) if per_page > 0 else 1

    # Format kết quả trả về
    combined_results = [dict(rec._mapping) for rec in records]
    for rec in combined_results:
        # Đổi tên key để phù hợp với frontend
        rec['id'] = rec.pop('id', None)
        rec['type'] = rec.pop('type', None)
        rec['thoi_gian'] = format_datetime_display(rec.pop('ThoiGian'), with_time=True) if rec.get('ThoiGian') else ""
        rec['ten_nguoi_thuc_hien'] = rec.pop('TenNguoiThucHien', None)
        rec['ma_nguoi_thuc_hien'] = rec.pop('MaNguoiThucHien', None)
        rec['ma_nv'] = rec.pop('MaNV', None)
        rec['ten_nv'] = rec.pop('TenNV', None)
        rec['chuc_vu'] = rec.pop('ChucVu', None)
        rec['chi_nhanh_chinh'] = rec.pop('ChiNhanhChinh', None)
        rec['chi_nhanh_lam'] = rec.pop('ChiNhanhLam', None)
        rec['so_cong'] = rec.pop('SoCong', None)
        rec['tang_ca'] = rec.pop('TangCa', None)
        rec['ghi_chu'] = rec.pop('GhiChu', None)
        rec['dich_vu'] = rec.pop('DichVu', None)
        rec['so_phong'] = rec.pop('SoPhong', None)
        rec['so_luong'] = rec.pop('SoLuong', None)

    return JSONResponse(content={
        "records": combined_results,
        "currentPage": page,
        "totalPages": total_pages,
        "totalRecords": total_records,
        # --- TỐI ƯU HÓA: Lấy dashboard_stats từ truy vấn thống kê riêng biệt ---
        "dashboard_stats": {
            "total_records": total_records,
            "total_work_units": float(stats_result.total_work_units or 0) if stats_result else 0,
            "total_overtime": stats_result.total_overtime if stats_result else 0,
            "total_services": int(stats_result.total_services or 0) if stats_result else 0,
            "total_absences": stats_result.total_absences if stats_result else 0,
        }
    })

@router.get("/api/today-checkins")
async def get_today_checkins(request: Request, db: Session = Depends(get_db)):
    """
    API mới để lấy danh sách nhân viên đã được điểm danh bởi người dùng hiện tại
    trong ngày làm việc hôm nay.
    """
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập.")

    checker_id = user_session.get("id")
    
    # Sử dụng get_current_work_shift để xác định ngày làm việc chính xác (xử lý ca đêm)
    from ..core.utils import get_current_work_shift
    from datetime import timedelta
    work_date, _ = get_current_work_shift()

    # Lấy các bản ghi điểm danh và dịch vụ do người dùng hiện tại tạo trong ngày làm việc
    # Query cho AttendanceRecord, join với Branch để lấy tên chi nhánh
    att_q = select(
        AttendanceRecord.employee_code_snapshot,
        AttendanceRecord.employee_name_snapshot,
        AttendanceRecord.role_snapshot,
        AttendanceRecord.attendance_datetime.label("datetime"),
        AttendanceRecord.work_units,
        AttendanceRecord.is_overtime,
        AttendanceRecord.notes,
        Branch.branch_code.label("branch_name")
    ).join(Branch, AttendanceRecord.branch_id == Branch.id).where(
        AttendanceRecord.checker_id == checker_id,
        cast(AttendanceRecord.attendance_datetime, Date) >= work_date,
        cast(AttendanceRecord.attendance_datetime, Date) < work_date + timedelta(days=1)
    )

    # Query cho ServiceRecord, join với Branch để lấy tên chi nhánh
    svc_q = select(
        ServiceRecord.employee_code_snapshot,
        ServiceRecord.employee_name_snapshot,
        ServiceRecord.role_snapshot,
        ServiceRecord.service_datetime.label("datetime"),
        literal_column("NULL").cast(Float).label("work_units"),
        ServiceRecord.is_overtime,
        ServiceRecord.notes,
        Branch.branch_code.label("branch_name")
    ).join(Branch, ServiceRecord.branch_id == Branch.id).where(
        ServiceRecord.checker_id == checker_id,
        cast(ServiceRecord.service_datetime, Date) >= work_date,
        cast(ServiceRecord.service_datetime, Date) < work_date + timedelta(days=1)
    )

    # Gộp, sắp xếp và thực thi
    all_records_q = union_all(att_q, svc_q)
    final_query = select(all_records_q.c).order_by(desc(all_records_q.c.datetime))
    records = db.execute(final_query).all()

    # Chuyển đổi kết quả thành list of dicts
    results = [dict(rec._mapping) for rec in records]

    return JSONResponse(content=jsonable_encoder({"work_date": work_date, "checkins": results}))

@router.get("/results", response_class=HTMLResponse)
def view_attendance_results(request: Request, db: Session = Depends(get_db)):
    """
    Route để hiển thị trang xem kết quả điểm danh.
    """
    if not require_checked_in_user(request):
        return RedirectResponse("/login", status_code=303)

    user_data = request.session.get("user")
    
    # Tạo một bản sao của ROLE_MAP và loại bỏ vai trò 'khac' để không hiển thị trong bộ lọc
    roles_for_filter = {k: v for k, v in ROLE_MAP.items() if k != 'khac'}

    return templates.TemplateResponse("results.html", {
        "request": request,
        "user": user_data,
        "branches": BRANCHES,
        "roles": roles_for_filter,
        "active_page": "attendance-results", # Đã có
    })

@router.delete("/api/record/{record_type}/{record_id}", response_class=JSONResponse)
def delete_record(
    record_type: str,
    record_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    API để xóa một bản ghi điểm danh hoặc dịch vụ cụ thể.
    Chỉ dành cho admin/boss.
    """
    user_session = request.session.get("user")
    if not user_session or user_session.get("role") not in ["admin", "boss"]:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện hành động này.")

    if record_type == 'attendance':
        record_to_delete = db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
    elif record_type == 'service':
        record_to_delete = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
    else:
        raise HTTPException(status_code=400, detail="Loại bản ghi không hợp lệ.")

    if not record_to_delete:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi để xóa.")

    try:
        db.delete(record_to_delete)
        db.commit()
        return JSONResponse(content={"status": "success", "message": "Đã xóa bản ghi thành công."})
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Lỗi khi xóa bản ghi (type: {record_type}, id: {record_id}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi server khi xóa bản ghi.")

@router.delete("/api/records/batch-delete", response_class=JSONResponse)
async def delete_records_batch(request: Request, db: Session = Depends(get_db)):
    """API để xóa hàng loạt các bản ghi."""
    user_session = request.session.get("user")
    if not user_session or user_session.get("role") not in ["admin", "boss"]:
        raise HTTPException(status_code=403, detail="Không có quyền thực hiện hành động này.")

    try:
        data = await request.json()
        records_to_delete = data.get("records", [])
        
        att_ids = [r['id'] for r in records_to_delete if r['type'] == 'attendance']
        svc_ids = [r['id'] for r in records_to_delete if r['type'] == 'service']

        deleted_count = 0
        if att_ids:
            # === SỬA LỖI: Thay đổi 'False' thành 'fetch' ===
            deleted_count += db.query(AttendanceRecord).filter(AttendanceRecord.id.in_(att_ids)).delete(synchronize_session='fetch')
        if svc_ids:
            # === SỬA LỖI: Thay đổi 'False' thành 'fetch' ===
            deleted_count += db.query(ServiceRecord).filter(ServiceRecord.id.in_(svc_ids)).delete(synchronize_session='fetch')

        db.commit()
        return JSONResponse(content={"status": "success", "deleted_count": deleted_count})
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi xóa hàng loạt bản ghi: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

@router.post("/api/manual-record", response_class=JSONResponse)
async def add_manual_record(
    request: Request,
    db: Session = Depends(get_db),
    record_type: str = Form(...),
    ma_nv: str = Form(...),
    thoi_gian: str = Form(...),
    nguoi_thuc_hien: Optional[str] = Form(None),
    chi_nhanh_lam: Optional[str] = Form(None),
    la_tang_ca: bool = Form(False),
    ghi_chu: Optional[str] = Form(""),
    so_cong_nv: Optional[float] = Form(1.0),
    dich_vu: Optional[str] = Form(""),
    so_phong: Optional[str] = Form(""),
    so_luong: Optional[str] = Form(""),
):
    session_user = request.session.get("user")
    if not session_user or session_user.get("role") not in ["admin", "boss"]:
        raise HTTPException(status_code=403, detail="Chỉ admin hoặc boss mới có quyền thực hiện.")

    employee = db.query(User).filter(User.employee_code == ma_nv).first()
    if not employee:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy nhân viên với mã: {ma_nv}")

    dt_obj = parse_form_datetime(thoi_gian)
    if not dt_obj:
        raise HTTPException(status_code=400, detail="Định dạng thời gian không hợp lệ. Cần: dd/mm/yyyy HH:MM")

    checker = db.query(User).filter(User.employee_code == nguoi_thuc_hien).first()
    if not checker:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy người thực hiện với mã: {nguoi_thuc_hien}")

    branch_obj = db.query(Branch).filter(Branch.branch_code == chi_nhanh_lam).first()
    if not branch_obj:
        raise HTTPException(status_code=400, detail=f"Chi nhánh làm việc không hợp lệ: {chi_nhanh_lam}")

    common_data = {
        "user_id": employee.id,
        "checker_id": checker.id,
        "branch_id": branch_obj.id,
        "is_overtime": la_tang_ca,
        "notes": ghi_chu,
        "employee_code_snapshot": employee.employee_code,
        "employee_name_snapshot": employee.name,
        "role_snapshot": ROLE_MAP.get(employee.department.role_code, employee.department.name) if employee.department else '',
        "main_branch_snapshot": employee.main_branch.branch_code if employee.main_branch else '',
    }

    try:
        if record_type == 'attendance':
            new_record = AttendanceRecord(
                **common_data,
                attendance_datetime=dt_obj,
                work_units=so_cong_nv or 1.0,
            )
        elif record_type == 'service':
            so_luong_str = str(so_luong or '')
            new_record = ServiceRecord(
                **common_data,
                service_datetime=dt_obj,
                service_type=dich_vu,
                room_number=so_phong,
                quantity=int(so_luong_str) if so_luong_str.isdigit() else None
            )
        else:
            raise HTTPException(status_code=400, detail="Loại bản ghi không hợp lệ.")
        
        db.add(new_record)
        db.commit()
        return JSONResponse({"status": "success", "message": "Đã thêm bản ghi thành công."})
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Lỗi khi thêm bản ghi mới: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi cơ sở dữ liệu: {e}")

@router.post("/api/manual-record/{record_type}/{record_id}", response_class=JSONResponse)
async def update_manual_record(
    record_type: str,
    record_id: int,
    request: Request,
    db: Session = Depends(get_db),
    ma_nv: str = Form(...),
    thoi_gian: str = Form(...),
    nguoi_thuc_hien: Optional[str] = Form(None),
    chi_nhanh_lam: Optional[str] = Form(None),
    la_tang_ca: bool = Form(False),
    ghi_chu: Optional[str] = Form(""),
    so_cong_nv: Optional[float] = Form(1.0),
    dich_vu: Optional[str] = Form(""),
    so_phong: Optional[str] = Form(""),
    so_luong: Optional[str] = Form(""),
):
    session_user = request.session.get("user")
    if not session_user or session_user.get("role") not in ["admin", "boss"]:
        raise HTTPException(status_code=403, detail="Chỉ admin hoặc boss mới có quyền thực hiện.")

    # 1. Sửa lỗi: Sử dụng `employee_code` thay vì `code`
    employee = db.query(User).filter(User.employee_code == ma_nv).first()
    if not employee:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy nhân viên với mã: {ma_nv}")

    # 2. Sửa lỗi: Import và sử dụng hàm `parse_form_datetime`
    dt_obj = parse_form_datetime(thoi_gian)
    if not dt_obj:
        raise HTTPException(status_code=400, detail="Định dạng thời gian không hợp lệ. Cần: dd/mm/yyyy HH:MM")

    # Sửa lỗi: Chỉ lấy mã từ chuỗi "Tên (Mã)"
    checker_code = nguoi_thuc_hien
    if nguoi_thuc_hien and '(' in nguoi_thuc_hien and ')' in nguoi_thuc_hien:
        checker_code = nguoi_thuc_hien.split('(')[-1].strip(')')

    # 3. Cập nhật logic để phù hợp với model mới
    checker = db.query(User).filter(User.employee_code == checker_code).first()
    if not checker:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy người thực hiện với mã: {checker_code}")

    branch_obj = db.query(Branch).filter(Branch.branch_code == chi_nhanh_lam).first()
    if not branch_obj:
        raise HTTPException(status_code=400, detail=f"Chi nhánh làm việc không hợp lệ: {chi_nhanh_lam}")

    # Dữ liệu snapshot chung
    common_snapshot_data = {
        "employee_code_snapshot": employee.employee_code,
        "employee_name_snapshot": employee.name,
        "role_snapshot": ROLE_MAP.get(employee.department.role_code, employee.department.name) if employee.department else '',
        "main_branch_snapshot": employee.main_branch.branch_code if employee.main_branch else '',
    }

    try:
        if record_type == 'attendance':
            record = db.query(AttendanceRecord).filter(AttendanceRecord.id == record_id).first()
            if not record:
                raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi điểm danh.")

            # Cập nhật các trường của AttendanceRecord
            record.user_id = employee.id
            record.checker_id = checker.id
            record.branch_id = branch_obj.id
            record.attendance_datetime = dt_obj
            record.work_units = so_cong_nv or 1.0
            record.is_overtime = la_tang_ca
            record.notes = ghi_chu
            # Cập nhật snapshot
            for key, value in common_snapshot_data.items():
                setattr(record, key, value)

        elif record_type == 'service':
            record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
            if not record:
                raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi dịch vụ.")

            # Cập nhật các trường của ServiceRecord
            record.user_id = employee.id
            record.checker_id = checker.id
            record.branch_id = branch_obj.id
            record.service_datetime = dt_obj
            record.service_type = dich_vu
            record.room_number = so_phong
            so_luong_str = str(so_luong or '')
            record.quantity = int(so_luong_str) if so_luong_str.isdigit() else None
            record.is_overtime = la_tang_ca
            record.notes = ghi_chu
            # Cập nhật snapshot
            for key, value in common_snapshot_data.items():
                setattr(record, key, value)

        else:
            raise HTTPException(status_code=400, detail="Loại bản ghi không hợp lệ.")
        
        db.commit()
        return JSONResponse({"status": "success", "message": "Đã cập nhật bản ghi thành công."})
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Lỗi khi cập nhật bản ghi: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi cơ sở dữ liệu: {e}")