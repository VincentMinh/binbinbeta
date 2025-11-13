# app/api/lost_and_found.py
# (ĐÃ CẬP NHẬT HOÀN CHỈNH CHO INSTANT UI)

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta
import math

# Import từ các module đã tái cấu trúc
from ..db.session import get_db
from ..db.models import User, LostAndFoundItem, Branch, Department, LostItemStatus
from ..core.security import get_active_branch
from ..core.config import logger, STATUS_MAP, BRANCHES
from ..core.utils import VN_TZ

from ..services.lost_and_found_service import update_disposable_items_status
# --- IMPORT CÁC SCHEMAS ---
from ..schemas.lost_and_found import (
    LostItemCreate, LostItemUpdate, BatchDeleteLostItemsPayload,
    LostItemsResponse, LostItemDetails
)

# Import các thành phần SQLAlchemy cần thiết
from sqlalchemy import cast, Date, desc, or_, asc, case, func, tuple_
from fastapi.encoders import jsonable_encoder
import os

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục gốc của project 'app'
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tạo đường dẫn tuyệt đối đến thư mục templates
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

def map_status_to_vietnamese(status_value: Optional[str]) -> str:
    """Helper to map status enum value to Vietnamese string."""
    if not status_value:
        return ""
    return STATUS_MAP.get(status_value, status_value)

# --- SỬA: Di chuyển helper _serialize_item lên đây ---
def _serialize_item(item: LostAndFoundItem) -> dict:
    """
    Helper để chuyển đổi một đối tượng LostAndFoundItem (đã load quan hệ) 
    thành dict có thể JSON hóa.
    """
    item_details = LostItemDetails.from_orm(item)
    item_details.return_date = item.return_datetime
    item_details.deleted_datetime = item.deleted_datetime
    item_details.chi_nhanh = item.branch.branch_code if item.branch else None
    item_details.reported_by = f"{item.reporter.name} ({item.reporter.employee_code})" if item.reporter else None
    item_details.recorded_by = f"{item.recorder.name} ({item.recorder.employee_code})" if item.recorder else None
    item_details.disposed_by = f"{item.disposer.name} ({item.disposer.employee_code})" if item.disposer else None
    item_details.deleted_by = f"{item.deleter.name} ({item.deleter.employee_code})" if item.deleter else None
    item_details.status = map_status_to_vietnamese(item.status.value if item.status else None)
    return jsonable_encoder(item_details)

def _get_filtered_lost_items(
    db: Session,
    user_data: dict,
    per_page: int,
    search: Optional[str] = None,
    status: Optional[str] = None,
    chi_nhanh: Optional[str] = None,
    found_date: Optional[str] = None,
    reported_by: Optional[str] = None,
    # --- THÊM: Tham số cho Keyset Pagination ---
    last_found_datetime: Optional[str] = None,
    last_id: Optional[int] = None,
    page: Optional[int] = 1, # Giữ lại để tải trang đầu tiên
    active_branch_for_letan: Optional[str] = None
) -> (List[LostAndFoundItem], int):
    """
    Hàm dịch vụ để lấy danh sách các món đồ thất lạc đã được lọc và phân trang.
    Hàm này đóng gói tất cả logic truy vấn để tái sử dụng.
    """
    query = db.query(LostAndFoundItem).options(
        joinedload(LostAndFoundItem.branch),
        joinedload(LostAndFoundItem.reporter),
        joinedload(LostAndFoundItem.recorder),
        joinedload(LostAndFoundItem.disposer),
        joinedload(LostAndFoundItem.deleter)
    )

    if user_data.get("role") not in ["admin", "boss"]:
        query = query.filter(LostAndFoundItem.status != LostItemStatus.DELETED)

    branch_to_filter = chi_nhanh
    if user_data.get("role") == 'letan' and not chi_nhanh:
        branch_to_filter = active_branch_for_letan

    if branch_to_filter:
        query = query.join(LostAndFoundItem.branch).filter(Branch.branch_code == branch_to_filter)

    if status:
        if status == "DELETED": # Xử lý giá trị đặc biệt từ bộ lọc của admin
            query = query.filter(LostAndFoundItem.status == LostItemStatus.DELETED)
        else:
            query = query.filter(LostAndFoundItem.status == status)

    if found_date:
        try:
            filter_date = datetime.strptime(found_date, "%Y-%m-%d").date()
            start_of_day = datetime.combine(filter_date, datetime.min.time()).replace(tzinfo=VN_TZ)
            end_of_day = datetime.combine(filter_date, datetime.max.time()).replace(tzinfo=VN_TZ)
            query = query.filter(LostAndFoundItem.found_datetime.between(start_of_day, end_of_day))
        except ValueError:
            logger.warning(f"Định dạng ngày không hợp lệ cho bộ lọc: {found_date}")

    if search:
        # SỬA LỖI: Sử dụng plainto_tsquery thay vì to_tsquery để xử lý an toàn các ký tự đặc biệt.
        # plainto_tsquery sẽ tự động chuyển đổi chuỗi tìm kiếm thành các từ khóa và nối chúng bằng toán tử AND (&).
        search_term = search.strip()
        if search_term:
            query = query.filter(LostAndFoundItem.fts_vector.op("@@")(func.plainto_tsquery('simple', search_term)))

    if reported_by:
        search_term = reported_by.strip()
        if '(' in search_term and ')' in search_term:
            search_term = search_term.split('(')[-1].strip(')')
        search_pattern = f"%{search_term}%"
        query = query.join(LostAndFoundItem.reporter).filter(
            or_(User.name.ilike(search_pattern), User.employee_code.ilike(search_pattern))
        )

    status_order = case(
        (LostAndFoundItem.status == LostItemStatus.STORED, 1),
        (LostAndFoundItem.status == LostItemStatus.DISPOSABLE, 2),
        (LostAndFoundItem.status == LostItemStatus.RETURNED, 3),
        (LostAndFoundItem.status == LostItemStatus.DISPOSED, 4),
        (LostAndFoundItem.status == LostItemStatus.DELETED, 5),
        else_=6
    )
    order_expression = desc(LostAndFoundItem.found_datetime)
    # --- THÊM: id làm tie-breaker, cực kỳ quan trọng cho keyset pagination ---
    id_order_expression = desc(LostAndFoundItem.id)

    # --- SỬA: Bỏ COUNT(*), thay bằng logic Keyset Pagination ---
    count_q = query.with_entities(func.count(LostAndFoundItem.id)).order_by(None)
    total_records = db.execute(count_q).scalar_one()

    # Áp dụng sắp xếp
    query = query.order_by(status_order, order_expression, id_order_expression)

    # Áp dụng Keyset Pagination nếu có cursor
    if last_found_datetime and last_id is not None:
        try:
            # Chuyển đổi cursor từ string ISO format về datetime object
            cursor_dt = datetime.fromisoformat(last_found_datetime)
            
            # Xây dựng điều kiện WHERE phức tạp cho Keyset Pagination
            # Điều này tương đương với: WHERE (found_datetime, id) < (last_found_datetime, last_id)
            # nhưng xử lý được các hướng sắp xếp khác nhau (DESC, DESC)
            query = query.filter(
                tuple_(LostAndFoundItem.found_datetime, LostAndFoundItem.id) < (cursor_dt, last_id)
            )
        except (ValueError, TypeError):
            logger.warning(f"Cursor không hợp lệ: last_found_datetime={last_found_datetime}, last_id={last_id}")
            query = query.offset((page - 1) * per_page) # Fallback về offset nếu cursor lỗi
    elif page > 1:
        # Chỉ dùng offset cho các trang sau trang 1 nếu không có cursor (trường hợp fallback)
        query = query.offset((page - 1) * per_page)

    items = query.limit(per_page).all()
    return items, total_records

# ----------------------------------------------------------------------
# ENDPOINT TẢI TRANG (GIỮ NGUYÊN)
# ----------------------------------------------------------------------
@router.get("", response_class=HTMLResponse)
async def lost_and_found_page(
    request: Request,
    db: Session = Depends(get_db),
    page: int = 1,
    per_page: int = 9,
    chi_nhanh: Optional[str] = None,
    status: Optional[str] = None,
):
    user_data = request.session.get("user")
    if not user_data:
        return RedirectResponse("/login", status_code=303)

    per_page = int(request.cookies.get('lostAndFoundPerPage', 9))

    if user_data.get("role") in ["admin", "boss", "quanly", "letan"]:
        try:
            update_disposable_items_status(db=db)
            db.commit() 
        except Exception as e:
            db.rollback() 
            logger.error(f"Lỗi khi cập nhật trạng thái đồ thất lạc: {e}", exc_info=True)

    all_branches_obj = db.query(Branch).filter(func.lower(Branch.branch_code).notin_(['admin', 'boss'])).all()

    b_branches = []
    other_branches = []
    for b in all_branches_obj:
        branch_code = b.branch_code
        if branch_code.startswith('B') and branch_code[1:].isdigit():
            b_branches.append(branch_code)
        else:
            other_branches.append(branch_code)
    b_branches.sort(key=lambda x: int(x[1:]))
    other_branches.sort()
    display_branches = b_branches + other_branches

    active_branch = "" 
    if user_data.get("role") == 'letan':
        active_branch = get_active_branch(request, db, user_data)

    status_display_map = {
        s.value: map_status_to_vietnamese(s.value) 
        for s in LostItemStatus if s != LostItemStatus.DELETED
    }
    
    # --- SỬA: SỬ DỤNG HÀM DỊCH VỤ ĐỂ LẤY DỮ LIỆU BAN ĐẦU ---
    branch_to_filter = chi_nhanh
    if user_data.get("role") == 'letan' and not chi_nhanh:
        active_branch = get_active_branch(request, db, user_data)
        branch_to_filter = active_branch

    items, total_records = _get_filtered_lost_items(
        db=db,
        user_data=user_data,
        per_page=per_page,
        page=page,
        chi_nhanh=branch_to_filter,
        status=status,
        # Các tham số khác có thể được thêm vào đây nếu cần lọc ban đầu
        active_branch_for_letan=active_branch
    )
    
    initial_records = [_serialize_item(item) for item in items]
    total_pages = math.ceil(total_records / per_page) if per_page > 0 else 1
    # --- KẾT THÚC SỬA ---

    return templates.TemplateResponse("lost_and_found.html", {
        "request": request,
        "user": user_data,
        "statuses": [s for s in LostItemStatus if s != LostItemStatus.DELETED],
        "initial_branch_filter": active_branch,
        "status_display_map": status_display_map, 
        "branches": display_branches, 
        "display_branches": display_branches,
        "branch_filter": chi_nhanh,
        "status_filter": status,
        # --- SỬA: Truyền dữ liệu ban đầu vào template ---
        "initial_records": initial_records,
        "current_page": page,
        "total_pages": total_pages,
        "total_records": total_records,
        "per_page": per_page,
        "active_page": "lost-and-found", # Đã có
    })

# ----------------------------------------------------------------------
# ENDPOINT API CHO DASHBOARD
# ----------------------------------------------------------------------
@router.get("/api/dashboard-stats")
async def get_dashboard_stats(
    request: Request,
    db: Session = Depends(get_db),
    chi_nhanh: Optional[str] = None,
    days: int = 30 # Mặc định lấy dữ liệu 30 ngày gần nhất
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Lọc theo vai trò
    branch_to_filter = chi_nhanh
    if user_data.get("role") == 'letan' and not chi_nhanh:
        branch_to_filter = get_active_branch(request, db, user_data)

    # Query cơ bản
    query = db.query(
        LostAndFoundItem.status,
        func.count(LostAndFoundItem.id).label('count')
    ).filter(LostAndFoundItem.status != LostItemStatus.DELETED)

    # Lọc theo chi nhánh nếu có
    if branch_to_filter:
        query = query.join(Branch).filter(Branch.branch_code == branch_to_filter)

    # --- SỬA LỖI LOGIC: Tính toán ngày bắt đầu LỌC cho cả 2 query ---
    query_start_datetime = None
    if days > 0:
        # Lấy N ngày, bao gồm cả hôm nay. 
        # VD: days=7 -> (now - 6 days) -> 7 ngày
        query_start_date = (datetime.now(VN_TZ) - timedelta(days=days - 1)).date()
        query_start_datetime = datetime.combine(query_start_date, datetime.min.time()).replace(tzinfo=VN_TZ)

    # Lọc theo khoảng thời gian cho query TỔNG QUAN
    if query_start_datetime:
        query = query.filter(LostAndFoundItem.found_datetime >= query_start_datetime)

    # Group by và thực thi
    stats = query.group_by(LostAndFoundItem.status).all()

    # Chuyển đổi kết quả (Giữ nguyên)
    stats_dict = {
        "total": 0,
        LostItemStatus.STORED.value: 0,
        LostItemStatus.DISPOSABLE.value: 0,
        LostItemStatus.RETURNED.value: 0,
        LostItemStatus.DISPOSED.value: 0,
    }
    for status, count in stats:
        if status.value in stats_dict:
            stats_dict[status.value] = count
    
    stats_dict["total"] = sum(stats_dict.values())

    # Lấy thêm thống kê theo ngày
    daily_query = db.query(
        cast(LostAndFoundItem.found_datetime, Date).label('date'),
        func.count(LostAndFoundItem.id).label('count')
    ).filter(LostAndFoundItem.status != LostItemStatus.DELETED)

    if branch_to_filter:
        daily_query = daily_query.join(Branch).filter(Branch.branch_code == branch_to_filter)
    
    # --- SỬA LỖI LOGIC: Áp dụng cùng ngày bắt đầu cho query BIỂU ĐỒ ---
    if query_start_datetime:
        daily_query = daily_query.filter(LostAndFoundItem.found_datetime >= query_start_datetime)

    # Nhóm và sắp xếp các kết quả
    daily_stats_raw = daily_query.group_by('date').order_by('date').all()

    # Chuẩn bị dữ liệu cho biểu đồ đường
    labels = []
    data = []
    stats_by_date = {stat.date: stat.count for stat in daily_stats_raw}

    # --- SỬA LỖI LOGIC: Tính toán ngày bắt đầu và kết thúc cho VÒNG LẶP ---
    
    # 1. Xác định ngày kết thúc
    end_date_iter = datetime.now(VN_TZ).date()
    
    # 2. Xác định ngày bắt đầu
    if days > 0:
        # Lấy N ngày, bao gồm cả hôm nay. (ĐÃ TÍNH Ở TRÊN)
        # Gán lại start_date_iter từ query_start_date
        start_date_iter = query_start_date
    else: # Trường hợp days = 0 (Tất cả)
        # Lấy ngày bắt đầu dựa trên bộ lọc chi nhánh hiện tại
        first_record_date_query = db.query(func.min(LostAndFoundItem.found_datetime))
        if branch_to_filter:
            first_record_date_query = first_record_date_query.join(Branch).filter(Branch.branch_code == branch_to_filter)
        
        first_record_date = first_record_date_query.scalar()
        if first_record_date:
            start_date_iter = first_record_date.astimezone(VN_TZ).date()
        else:
            start_date_iter = end_date_iter # Mặc định là hôm nay nếu không có bản ghi nào

    # 3. Tạo vòng lặp (BÂY GIỜ ĐÃ ĐỒNG BỘ VỚI TRUY VẤN)
    date_iter = start_date_iter
    while date_iter <= end_date_iter:
        labels.append(date_iter.strftime("%d/%m"))
        data.append(stats_by_date.get(date_iter, 0))
        date_iter += timedelta(days=1)
    # --- KẾT THÚC PHẦN SỬA LỖI ---

    return JSONResponse({
        "status_stats": stats_dict,
        "daily_stats": {
            "labels": labels,
            "data": data
        }
    })

# ----------------------------------------------------------------------
# ENDPOINT API LẤY DỮ LIỆU (SỬA: DÙNG _serialize_item)
# ----------------------------------------------------------------------
@router.get("/api", response_model=LostItemsResponse)
async def api_lost_and_found_items( 
    request: Request, 
    db: Session = Depends(get_db),
    page: int = 1, # THÊM: Nhận tham số page
    per_page: int = 20,
    search: Optional[str] = None,
    status: Optional[str] = None,
    chi_nhanh: Optional[str] = None,
    found_date: Optional[str] = None,
    reported_by: Optional[str] = None, 
    # --- THÊM: Tham số cursor cho API ---
    last_found_datetime: Optional[str] = None,
    last_id: Optional[int] = None,
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # --- SỬA: SỬ DỤNG HÀM DỊCH VỤ ĐỂ LẤY DỮ LIỆU ---
    active_branch_for_letan = None
    if user_data.get("role") == 'letan' and not chi_nhanh:
        active_branch_for_letan = get_active_branch(request, db, user_data)

    items, total_records = _get_filtered_lost_items(
        db=db,
        user_data=user_data,
        per_page=per_page,
        page=page, # THÊM: Truyền page vào hàm filter
        search=search,
        status=status,
        chi_nhanh=chi_nhanh,
        found_date=found_date,
        reported_by=reported_by,
        last_found_datetime=last_found_datetime,
        last_id=last_id,
        active_branch_for_letan=active_branch_for_letan
    )
    
    # --- SỬA: Dùng _serialize_item cho nhất quán ---
    results = [_serialize_item(item) for item in items]

    return {
        "records": results,
        # SỬA: Trả về page đã nhận được, không gán cứng là 1
        "currentPage": page, 
        "totalPages": math.ceil(total_records / per_page) if per_page > 0 else 1,
        "totalRecords": total_records
    }

# ----------------------------------------------------------------------
# ENDPOINT THÊM MỚI (SỬA: Thêm refresh quan hệ)
# ----------------------------------------------------------------------
@router.post("/add", status_code=201, response_model=dict)
async def add_lost_item(
    request: Request,
    db: Session = Depends(get_db)
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Unauthorized")

    form_data = await request.form()
    
    item_name = form_data.get("item_name")
    found_location = form_data.get("found_location")

    chi_nhanh_code_from_form = form_data.get("chi_nhanh")
    reported_by_string = form_data.get("reported_by")
    recorded_by_string = form_data.get("recorded_by")

    reported_by_code = None
    if reported_by_string and '(' in reported_by_string and ')' in reported_by_string:
        reported_by_code = reported_by_string.split('(')[-1].strip(')')

    recorded_by_code = None
    if recorded_by_string and '(' in recorded_by_string and ')' in recorded_by_string:
        recorded_by_code = recorded_by_string.split('(')[-1].strip(')')

    recorder = None
    if recorded_by_code:
        recorder = db.query(User).filter(User.employee_code == recorded_by_code).first()
    if not recorder:
        recorder = db.query(User).filter(User.id == user_data["id"]).first()

    chi_nhanh_code = chi_nhanh_code_from_form # Ưu tiên chi nhánh từ form (cho Admin)
    
    if not chi_nhanh_code and user_data.get("role") == 'letan':
        # Nếu là Lễ tân và form không gửi chi nhánh,
        # hãy lấy chi nhánh đang hoạt động (active_branch) từ session.
        chi_nhanh_code = get_active_branch(request, db, user_data) # <--- SỬA Ở ĐÂY
    
    branch = db.query(Branch).filter(Branch.branch_code == chi_nhanh_code).first()
    # === KẾT THÚC SỬA LỖI ===

    if not reporter:
        raise HTTPException(status_code=400, detail=f"Không tìm thấy người báo cáo với mã: {reported_by_code}")
    if not branch:
        # Lỗi bây giờ sẽ rõ ràng hơn, ví dụ: "Không tìm thấy chi nhánh: B10"
        raise HTTPException(status_code=400, detail=f"Không tìm thấy chi nhánh: {chi_nhanh_code}")

    new_item = LostAndFoundItem(
        item_name=item_name,
        description=form_data.get("description"),
        found_location=found_location,
        owner_name=form_data.get("owner_name"),
        owner_contact=form_data.get("owner_contact"),
        notes=form_data.get("notes"),
        branch_id=branch.id,
        reporter_id=reporter.id,
        recorder_id=recorder.id,
        found_datetime=datetime.now(VN_TZ)
    )
    
    db.add(new_item)
    db.commit()
    # --- SỬA: Refresh các quan hệ cần thiết cho _serialize_item ---
    db.refresh(new_item, ["branch", "reporter", "recorder"]) 
    return {"status": "success", "message": "Đã thêm món đồ thành công.", "item": _serialize_item(new_item)}

# ----------------------------------------------------------------------
# ENDPOINT CHỈNH SỬA (SỬA: Thêm refresh quan hệ)
# ----------------------------------------------------------------------
@router.post("/edit-details/{item_id}", response_model=dict)
async def edit_lost_item_details(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    item_name: str = Form(...),
    description: Optional[str] = Form(None),
    found_location: str = Form(...),
    reported_by: str = Form(...), 
    recorded_by: Optional[str] = Form(None), 
    owner_name: str = Form(...),
    owner_contact: str = Form(...),
    notes: Optional[str] = Form(None),
    chi_nhanh: Optional[str] = Form(None),
    receiver_name: Optional[str] = Form(None),
    receiver_contact: Optional[str] = Form(None),
    disposed_amount: Optional[str] = Form(None), 
    update_notes: Optional[str] = Form(None),
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Unauthorized")

    allowed_roles = ["letan", "quanly", "admin", "boss"]
    if user_data.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Bạn không có quyền chỉnh sửa món đồ này.")

    item = db.query(LostAndFoundItem).filter(LostAndFoundItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy món đồ.")

    # (Giữ nguyên logic parse reported_by, recorded_by, branch)
    reported_by_code = None
    if reported_by and '(' in reported_by and ')' in reported_by:
        reported_by_code = reported_by.split('(')[-1].strip(')')
    reporter = db.query(User).filter(User.employee_code == reported_by_code).first()
    if not reporter:
        raise HTTPException(status_code=400, detail=f"Không tìm thấy người phát hiện với mã: {reported_by_code}")

    recorder = None
    if recorded_by: 
        if '(' in recorded_by and ')' in recorded_by:
            recorded_by_code = recorded_by.split('(')[-1].strip(')')
            recorder = db.query(User).filter(User.employee_code == recorded_by_code).first()
            if not recorder:
                raise HTTPException(status_code=400, detail=f"Không tìm thấy người ghi nhận với mã: {recorded_by_code}")
    else: 
        recorder = item.recorder

    #
    branch = None
    chi_nhanh_code_to_find = chi_nhanh # Ưu tiên giá trị từ form (cho Admin/QL)

    if not chi_nhanh_code_to_find and user_data.get("role") == 'letan':
        # Nếu là Lễ tân và form không có chi nhánh,
        # Lấy chi nhánh đang hoạt động (active_branch) từ session.
        chi_nhanh_code_to_find = get_active_branch(request, db, user_data)
    
    if not chi_nhanh_code_to_find:
         # Nếu sau tất cả vẫn không có mã chi nhánh (ví dụ: Admin không chọn)
         raise HTTPException(status_code=400, detail="Chi nhánh không hợp lệ hoặc không được cung cấp.")

    branch = db.query(Branch).filter(Branch.branch_code == chi_nhanh_code_to_find).first()
    if not branch:
        raise HTTPException(status_code=400, detail=f"Không tìm thấy chi nhánh: {chi_nhanh_code_to_find}")

    # (Giữ nguyên logic cập nhật item)
    item.item_name = item_name
    item.description = description
    item.found_location = found_location
    item.reported_by_id = reporter.id
    item.recorder_id = recorder.id if recorder else item.recorder_id 
    item.owner_name = owner_name
    item.owner_contact = owner_contact
    item.notes = notes
    item.branch_id = branch.id
    
    if item.status == LostItemStatus.RETURNED:
        item.receiver_name = receiver_name
        item.receiver_contact = receiver_contact
        item.update_notes = update_notes

    elif item.status == LostItemStatus.DISPOSED:
        try:
            item.disposed_amount = int(disposed_amount) if disposed_amount and disposed_amount.isdigit() else None
        except (ValueError, TypeError):
            item.disposed_amount = None
        item.update_notes = update_notes

    db.commit()
    # --- SỬA: Refresh TẤT CẢ các quan hệ có thể đã thay đổi ---
    db.refresh(item, ["branch", "reporter", "recorder", "disposer", "deleter"])
    return {"status": "success", "message": "Đã cập nhật món đồ thành công.", "item": _serialize_item(item)}

# ----------------------------------------------------------------------
# ENDPOINT CẬP NHẬT TRẠNG THÁI (SỬA: Thêm refresh quan hệ)
# ----------------------------------------------------------------------
@router.post("/update/{item_id}", response_model=dict)
async def update_lost_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    action: str = Form(...),
    owner_name: Optional[str] = Form(None),
    owner_contact: Optional[str] = Form(None),
    disposed_by: Optional[str] = Form(None),
    disposed_amount: Optional[str] = Form(None), 
    notes: Optional[str] = Form(None),
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Unauthorized")

    item = db.query(LostAndFoundItem).filter(LostAndFoundItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy món đồ.")
    
    allowed_roles = ["letan", "quanly", "admin", "boss"]
    if user_data.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện hành động này.")

    now = datetime.now(VN_TZ)
    
    # (Giữ nguyên logic cập nhật)
    item.update_notes = notes.strip() if notes else None 

    if action == "return":
        item.status = LostItemStatus.RETURNED
        item.receiver_name = owner_name
        item.receiver_contact = owner_contact
        item.return_datetime = now
    
    elif action == "dispose":
        disposer_code = None
        if disposed_by and '(' in disposed_by and ')' in disposed_by:
            disposer_code = disposed_by.split('(')[-1].strip(')')
        
        disposer = db.query(User).filter(User.employee_code == disposer_code).first() if disposer_code else None
        if not disposer:
            raise HTTPException(status_code=400, detail=f"Không tìm thấy người thanh lý với mã: {disposer_code}")
        
        item.status = LostItemStatus.DISPOSED
        item.disposer_id = disposer.id
        
        try:
            if disposed_amount and disposed_amount.isdigit():
                item.disposed_amount = int(disposed_amount)
            else:
                item.disposed_amount = None
        except (ValueError, TypeError):
            item.disposed_amount = None

        item.return_datetime = now
        
    db.commit()
    # --- SỬA: Refresh TẤT CẢ các quan hệ ---
    db.refresh(item, ["branch", "reporter", "recorder", "disposer", "deleter"])
    return {"status": "success", "message": "Đã cập nhật trạng thái.", "item": _serialize_item(item)}

# ----------------------------------------------------------------------
# ENDPOINT XÓA (SỬA: Trả về JSON cho Instant UI)
# ----------------------------------------------------------------------
@router.post("/delete/{item_id}", response_class=JSONResponse)
async def delete_lost_item(
    item_id: int, 
    request: Request, 
    db: Session = Depends(get_db),
    hard_delete: bool = Form(False) 
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Unauthorized")

    item = db.query(LostAndFoundItem).filter(LostAndFoundItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    user_role = user_data.get("role")
    now = datetime.now(VN_TZ)

    if user_role in ["admin", "boss"] and hard_delete:
        # Xóa vĩnh viễn
        item_id_to_return = item.id # Ghi lại ID trước khi xóa
        db.delete(item)
        db.commit()
        return JSONResponse({
            "status": "success", 
            "message": "Đã xóa vĩnh viễn món đồ.",
            "deleted_id": item_id_to_return, # Trả về ID đã xóa
            "hard_delete": True
        })
    else:
        # Xóa mềm (soft delete)
        item.status = LostItemStatus.DELETED
        item.deleter_id = user_data.get("id")
        item.deleted_datetime = now
        db.commit()
        # Refresh để lấy tất cả quan hệ, bao gồm 'deleter'
        db.refresh(item, ["branch", "reporter", "recorder", "disposer", "deleter"])
        return JSONResponse({
            "status": "success", 
            "message": "Đã xóa món đồ thành công.",
            "item": _serialize_item(item), # Trả về item đã cập nhật
            "hard_delete": False
        })

# ----------------------------------------------------------------------
# ENDPOINT XÓA HÀNG LOẠT (SỬA: Trả về JSON cho Instant UI)
# ----------------------------------------------------------------------
@router.post("/batch-delete", response_model=dict)
async def batch_delete_lost_items(
    payload: BatchDeleteLostItemsPayload,
    request: Request,
    db: Session = Depends(get_db)
):
    user_data = request.session.get("user")
    user_role = user_data.get("role") if user_data else None
    if not user_role:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if not payload.ids:
        return JSONResponse({"status": "noop", "message": "Không có mục nào được chọn để xóa."})

    ids_to_process = payload.ids
    try:
        if user_role in ["admin", "boss"]:
            # Admin/Boss: Xóa vĩnh viễn
            num_deleted = db.query(LostAndFoundItem).filter(LostAndFoundItem.id.in_(ids_to_process)).delete(synchronize_session=False)
            db.commit()
            return JSONResponse({
                "status": "success", 
                "message": f"Đã xóa vĩnh viễn {num_deleted} mục.",
                "ids": ids_to_process, # Trả về mảng các ID đã xóa
                "hard_delete": True
            })
        else:
            # Các vai trò khác: Xóa mềm
            now = datetime.now(VN_TZ)
            deleter_id = user_data.get("id")
            
            num_updated = db.query(LostAndFoundItem).filter(
                LostAndFoundItem.id.in_(ids_to_process)
            ).update({
                "status": LostItemStatus.DELETED.value,
                "deleter_id": deleter_id,
                "deleted_datetime": now
            }, synchronize_session=False)
            
            db.commit()
            
            # Lấy lại các item vừa cập nhật để trả về cho frontend
            updated_items = db.query(LostAndFoundItem).options(
                joinedload(LostAndFoundItem.branch),
                joinedload(LostAndFoundItem.reporter),
                joinedload(LostAndFoundItem.recorder),
                joinedload(LostAndFoundItem.disposer),
                joinedload(LostAndFoundItem.deleter)
            ).filter(LostAndFoundItem.id.in_(ids_to_process)).all()
            
            serialized_items = [_serialize_item(item) for item in updated_items]

            return JSONResponse({
                "status": "success", 
                "message": f"Đã xóa thành công {num_updated} mục.",
                "ids": ids_to_process,
                "items": serialized_items, # Trả về mảng các item đã cập nhật
                "hard_delete": False
            })
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi xóa hàng loạt đồ thất lạc: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Lỗi server khi xóa.")
