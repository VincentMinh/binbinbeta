from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, aliased, joinedload
from typing import Optional, List

# Import từ các module đã tái cấu trúc
from ..db.session import get_db
from ..db.models import User, Task, Branch, Department
from ..core.security import get_active_branch
from ..core.utils import format_datetime_display, VN_TZ, clean_query_string, parse_datetime_input
from ..services.task_service import get_task_stats
from ..core.config import logger
from ..schemas.task import Task as TaskSchema

# Import các thành phần SQLAlchemy cần thiết
from datetime import datetime, timedelta
import secrets, json
from sqlalchemy import case, or_, func
from urllib.parse import urlencode
import os

from ..core.config import DEPARTMENTS
from fastapi import Query
from datetime import date
from fastapi.encoders import jsonable_encoder

router = APIRouter()

# Xác định đường dẫn tuyệt đối đến thư mục gốc của project 'app'
# os.path.dirname(__file__) -> app/api
# os.path.join(..., "..") -> app/
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Tạo đường dẫn tuyệt đối đến thư mục templates
templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

def task_to_dict(t: Task) -> dict:
    """Hàm helper để chuyển đổi một đối tượng Task SQLAlchemy thành dict."""
    return {
        "id": t.id,
        "id_task": t.id_task,
        "chi_nhanh": t.branch.branch_code if t.branch else "N/A",
        "phong": t.room_number,
        "mo_ta": t.description,
        "department": t.department or "Chưa gán",
        "ngay_tao": format_datetime_display(t.created_at, with_time=True),
        "han_hoan_thanh": format_datetime_display(t.due_date, with_time=True),
        "han_hoan_thanh_raw": t.due_date.isoformat() if t.due_date else None,
        "trang_thai": t.status,
        "nguoi_tao": f"{t.author.name} ({t.author.employee_code})" if t.author else "N/A",
        "ghi_chu": t.notes or "",
        "nguoi_thuc_hien": t.assignee.name if t.assignee else "",
        "ngay_hoan_thanh": format_datetime_display(t.completed_at, with_time=True) if t.completed_at else "",
        "is_overdue": t.status == "Quá hạn",
    }

@router.get("/tasks", response_class=HTMLResponse)
def home(
    request: Request,
    chi_nhanh: str = "",
    search: str = "",
    trang_thai: str = "",
    han_hoan_thanh: str = "",
    bo_phan: str = "",
    page: int = 1,
    per_page: int = Query(10, ge=1, le=100), # Sửa: Nhận per_page từ query, mặc định là 10
    db: Session = Depends(get_db)
):
    user_data = request.session.get("user")
    today = datetime.now(VN_TZ)

    if not user_data:
        return RedirectResponse("/login", status_code=303)

    # Lấy thông tin user từ session theo cấu trúc mới
    user_employee_code = user_data["code"]
    user_role = user_data["role"]
    user_name = user_data["name"]

    user_from_db = db.query(User).filter(User.employee_code == user_employee_code).first()

    # Logic xác định chi nhánh hoạt động (giữ nguyên)
    active_branch = (
        request.session.get("active_branch")
        or (user_from_db.last_active_branch if user_from_db else None)
        or user_data.get("branch")
    )

    # Logic xác định chi nhánh để lọc query (giữ nguyên)
    branch_to_filter = chi_nhanh
    if user_role == 'letan' and not chi_nhanh:
        branch_to_filter = active_branch

    # Query công việc bằng hàm helper mới
    tasks_query = _get_filtered_tasks_query(
        db, user_data, branch_to_filter, search, trang_thai, han_hoan_thanh,bo_phan
    )

    total_tasks = tasks_query.count()
    total_pages = max(1, (total_tasks + per_page - 1) // per_page)

    # Sắp xếp (cập nhật tên cột)
    order = {"Quá hạn": 0, "Đang chờ": 1, "Hoàn thành": 2, "Đã xoá": 3}
    rows = (
        tasks_query.order_by(
            case(order, value=Task.status, else_=99),
            Task.due_date.nullslast(),
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Chuẩn bị dữ liệu để hiển thị (lấy từ relationship)
    tasks = []
    for t in rows:
        tasks.append({
            "id": t.id,
            "id_task": t.id_task, # Thêm ID công việc
            "chi_nhanh": t.branch.branch_code if t.branch else "N/A",
            "phong": t.room_number,
            "mo_ta": t.description,
            "department": t.department or "Chưa gán",
            "ngay_tao": format_datetime_display(t.created_at, with_time=True), # Giữ nguyên ngày tạo có giờ
            "han_hoan_thanh": format_datetime_display(t.due_date, with_time=True), # Sửa: Hạn hoàn thành có giờ
            "han_hoan_thanh_raw": t.due_date.isoformat() if t.due_date else None,
            "trang_thai": t.status,
            "nguoi_tao": f"{t.author.name} ({t.author.employee_code})" if t.author else "N/A", # Sửa: Thêm mã nhân viên
            "ghi_chu": t.notes or "",
            "nguoi_thuc_hien": t.assignee.name if t.assignee else "",
            "ngay_hoan_thanh": format_datetime_display(t.completed_at, with_time=True) if t.completed_at else "",
            "nguoi_xoa": t.deleter.name if t.deleter else "",
            "ngay_xoa": format_datetime_display(t.deleted_at, with_time=True) if t.deleted_at else "",
            "is_overdue": t.status == "Quá hạn",
        })

    # === TỐI ƯU HÓA: Lấy tất cả thống kê trong một truy vấn duy nhất ===
    start_of_week = today.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=today.weekday())
    
    stats_result = tasks_query.with_entities(
        func.count(Task.id).label("total_tasks"),
        func.count(case((Task.status == "Hoàn thành", Task.id))).label("hoan_thanh"),
        func.count(case(((Task.status == "Hoàn thành") & (Task.completed_at >= start_of_week), Task.id))).label("hoan_thanh_tuan"),
        func.count(case(((Task.status == "Hoàn thành") & (func.extract("month", Task.completed_at) == today.month), Task.id))).label("hoan_thanh_thang"),
        func.count(case((Task.status == "Đang chờ", Task.id))).label("dang_cho"),
        func.count(case((Task.status == "Quá hạn", Task.id))).label("qua_han")
    ).first()

    thong_ke = {
        "tong_cong_viec": stats_result.total_tasks if stats_result else 0,
        "hoan_thanh": stats_result.hoan_thanh if stats_result else 0,
        "hoan_thanh_tuan": stats_result.hoan_thanh_tuan if stats_result else 0,
        "hoan_thanh_thang": stats_result.hoan_thanh_thang if stats_result else 0,
        "dang_cho": stats_result.dang_cho if stats_result else 0,
        "qua_han": stats_result.qua_han if stats_result else 0,
    }

    # Lấy danh sách chi nhánh từ DB và sắp xếp theo yêu cầu (B1, B2, B3...)
    all_branches_obj = db.query(Branch).filter(func.lower(Branch.branch_code).notin_(['admin', 'boss'])).all()

    # Logic sắp xếp chi nhánh tùy chỉnh
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

    # Tạo query string cho phân trang
    query_params = {
        "chi_nhanh": branch_to_filter, "search": search, "trang_thai": trang_thai,
        "han_hoan_thanh": han_hoan_thanh, "bo_phan": bo_phan, "per_page": per_page,
    }
    active_filters = {k: v for k, v in query_params.items() if v}
    pagination_query_string = urlencode(active_filters)

    # Render template
    response = templates.TemplateResponse(
        "tasks.html",
        {
            "request": request,
            "user": user_data, # Truyền toàn bộ đối tượng user
            "tasks": tasks,
            "user_name": user_name,
            "search": search,
            "trang_thai": trang_thai,
            "chi_nhanh": branch_to_filter,
            "user_chi_nhanh": active_branch,
            "branches": display_branches,
            "now": today,
            "thong_ke": thong_ke,
            "page": page,
            "total_pages": total_pages,
            "per_page": per_page,
            "total_tasks": total_tasks,
            "query_string": f"&{pagination_query_string}" if pagination_query_string else "",
            "han_hoan_thanh": han_hoan_thanh,
            "departments": DEPARTMENTS,
            "bo_phan": bo_phan,
            "active_page": "tasks" # Đã có
        }
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def _get_filtered_tasks_query(
    db: Session,
    user_data: dict,
    chi_nhanh: str = "",
    search: str = "",
    trang_thai: str = "",
    han_hoan_thanh: str = "",
    bo_phan: str = ""
):
    """
    Hàm helper phiên bản mới, query công việc dựa trên kiến trúc database chuẩn hóa.
    """
    Author = aliased(User, name="author")
    Assignee = aliased(User, name="assignee")

    # Bắt đầu query với options để load sẵn các relationship cần thiết
    tasks_query = db.query(Task).options(
        joinedload(Task.branch),
        joinedload(Task.author),
        joinedload(Task.assignee),
        joinedload(Task.deleter) # Thêm joinedload cho người xóa
    )

    # Chỉ join với các bảng cần thiết để lọc
    tasks_query = tasks_query.join(Task.branch)
    tasks_query = tasks_query.outerjoin(Author, Task.author)
    tasks_query = tasks_query.outerjoin(Assignee, Task.assignee)


    # Lọc theo trạng thái (loại bỏ "Đã xoá" cho vai trò không phải quản lý)
    role = user_data.get("role")
    if role not in ["quanly", "admin", "boss"]:
        tasks_query = tasks_query.filter(Task.status != "Đã xoá")

    # Lọc theo chi nhánh (dựa trên branch_code)
    if chi_nhanh:
        tasks_query = tasks_query.filter(Branch.branch_code == chi_nhanh)

    # Lọc theo từ khóa tìm kiếm
    if search:
        clean_search = f"%{search.strip()}%"
        tasks_query = tasks_query.filter(
            or_(
                Branch.name.ilike(clean_search),
                Task.id_task.ilike(clean_search), # Cho phép tìm kiếm theo ID công việc
                Task.room_number.ilike(clean_search),
                Task.description.ilike(clean_search),
                Task.status.ilike(clean_search),
                Author.name.ilike(clean_search),
                Assignee.name.ilike(clean_search),
                Task.notes.ilike(clean_search)
            )
        )

    # Lọc theo trạng thái cụ thể
    if trang_thai:
        tasks_query = tasks_query.filter(Task.status == trang_thai)

    if bo_phan:
        tasks_query = tasks_query.filter(Task.department == bo_phan)

    # Lọc theo hạn hoàn thành
    if han_hoan_thanh:
        try:
            # Sửa lỗi: Lọc theo khoảng thời gian của một ngày để đảm bảo chính xác
            # Thêm VN_TZ để tạo datetime "aware", đảm bảo so sánh đúng với dữ liệu trong DB
            start_of_day_naive = datetime.strptime(han_hoan_thanh, "%Y-%m-%d")
            start_of_day = VN_TZ.localize(start_of_day_naive)
            end_of_day = start_of_day + timedelta(days=1)
            tasks_query = tasks_query.filter(Task.due_date >= start_of_day)
            tasks_query = tasks_query.filter(Task.due_date < end_of_day)
        except (ValueError, TypeError):
            pass  # Bỏ qua nếu định dạng ngày không hợp lệ

    return tasks_query

@router.post("/add")
def add_task(
    request: Request,
    chi_nhanh: str = Form(...),
    vi_tri: str = Form(..., alias="phong"),
    mo_ta: str = Form(...),
    bo_phan: str = Form(...),
    han_hoan_thanh: str = Form(...),
    ghi_chu: str = Form(""),
    db: Session = Depends(get_db)
):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse("/login", status_code=303)

    # Lấy id của chi nhánh và người tạo
    branch = db.query(Branch).filter(Branch.branch_code == chi_nhanh).first()
    author = db.query(User).filter(User.id == user_session["id"]).first()

    if not branch or not author:
        raise HTTPException(status_code=400, detail="Chi nhánh hoặc người tạo không hợp lệ.")

    # Chuyển đổi ngày từ form và kết hợp với giờ hiện tại
    due_date_only = datetime.strptime(han_hoan_thanh, "%Y-%m-%d").date()
    now_time = datetime.now(VN_TZ).time()
    han = VN_TZ.localize(datetime.combine(due_date_only, now_time))

    trang_thai = "Quá hạn" if han < datetime.now(VN_TZ) else "Đang chờ"

    # --- LOGIC TẠO ID MỚI ---
    # Tạo ID công việc ngắn gọn và duy nhất, ví dụ: B1-A3B4C5
    while True:
        random_part = str(secrets.randbelow(100000)).zfill(5) # 5 chữ số ngẫu nhiên
        id_task = f"{chi_nhanh}-{random_part}"
        if not db.query(Task).filter(Task.id_task == id_task).first():
            break

    new_task = Task(
        id_task=id_task, # Lưu ID công việc
        branch_id=branch.id, 
        author_id=author.id, 
        room_number=vi_tri, # Sử dụng biến mới
        description=mo_ta,
        department=bo_phan, # <-- THÊM DÒNG NÀY
        due_date=han,
        status=trang_thai,
        notes=ghi_chu,
        created_at=datetime.now(VN_TZ)
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task) # Lấy dữ liệu mới nhất từ DB, bao gồm cả relationships

    if request.query_params.get("json") == "1":
        return JSONResponse({"success": True, "task": task_to_dict(new_task)})

    raw_query = request.scope.get("query_string", b"").decode()
    clean_query = clean_query_string(raw_query)
    redirect_url = f"/tasks?{clean_query}&success=1&action=add" if clean_query else "/tasks?success=1&action=add"

    return RedirectResponse(redirect_url, status_code=303)

@router.post("/complete/{task_id}")
async def complete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=403, detail="Unauthorized")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc")
    
    # Lấy thông tin người thực hiện từ session
    assignee_id = user_session.get("id")

    task.status = "Hoàn thành"
    task.assignee_id = assignee_id # <-- SỬA: Gán ID người thực hiện
    task.completed_at = datetime.now(VN_TZ) # <-- SỬA: Sử dụng múi giờ Việt Nam

    db.commit()

    if request.query_params.get("json") == "1":
        return JSONResponse({"success": True, "task_id": task_id})

    raw_query = request.scope.get("query_string", b"").decode()
    clean_query = clean_query_string(raw_query)
    # Sửa lỗi: Thêm dấu & nếu clean_query đã có tham số
    separator = '&' if clean_query else ''
    redirect_url = f"/tasks?{clean_query}{separator}success=1&action=complete"
    return RedirectResponse(url=redirect_url, status_code=303)

@router.post("/delete/{task_id}")
async def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse("/login", status_code=303)

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc")

    # Kiểm tra vai trò từ session
    if user_session.get("role") in ["quanly", "admin", "boss"]:
        db.delete(task)
    else:
        # Cập nhật trạng thái, người xóa và thời gian xóa
        deleter_id = user_session.get("id")
        task.status = "Đã xoá"
        task.deleter_id = deleter_id
        task.deleted_at = datetime.now(VN_TZ)
    
    db.commit()

    if request.query_params.get("json") == "1":
        return JSONResponse({"success": True, "task_id": task_id})

    raw_query = request.scope.get("query_string", b"").decode()
    clean_query = clean_query_string(raw_query)
    # Sửa lỗi: Thêm dấu & nếu clean_query đã có tham số
    separator = '&' if clean_query else ''
    redirect_url = f"/tasks?{clean_query}{separator}success=1&action=delete"
    return RedirectResponse(url=redirect_url, status_code=303)

@router.post("/delete/soft/{task_id}", response_class=JSONResponse)
async def soft_delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Endpoint mới chuyên cho việc xóa mềm (soft delete) và trả về dữ liệu JSON.
    """
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=403, detail="Unauthorized")

    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc")

    # Thực hiện xóa mềm
    task.status = "Đã xoá"
    task.deleter_id = user_session.get("id")
    task.deleted_at = datetime.now(VN_TZ)
    
    db.commit()
    db.refresh(task) # Refresh để lấy thông tin người xóa (deleter)

    # Trả về JSON với thông tin task đã được cập nhật
    return JSONResponse({
        "success": True, 
        "task": task_to_dict(task)
    })

@router.post("/api/tasks/batch-delete-permanent", response_class=JSONResponse)
async def batch_delete_permanent_tasks(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    API để xóa vĩnh viễn hàng loạt công việc.
    Chỉ dành cho admin/boss.
    """
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if user_session.get("role") not in ["admin", "boss"]:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện hành động này.")

    try:
        payload = await request.json()
        task_ids = payload.get("task_ids", [])
        if not task_ids:
            return JSONResponse({"success": False, "detail": "Không có công việc nào được chọn."}, status_code=400)

        deleted_count = db.query(Task).filter(Task.id.in_(task_ids)).delete(synchronize_session=False)
        db.commit()
        return JSONResponse({"success": True, "deleted_count": deleted_count})
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi xóa vĩnh viễn công việc hàng loạt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

@router.post("/api/tasks/batch-delete-soft", response_class=JSONResponse)
async def batch_delete_soft_tasks(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    API để xóa mềm hàng loạt công việc.
    Dành cho các vai trò không phải admin/boss.
    """
    user_session = request.session.get("user")
    if not user_session:
        raise HTTPException(status_code=403, detail="Unauthorized")

    try:
        payload = await request.json()
        task_ids = payload.get("task_ids", [])
        if not task_ids:
            return JSONResponse({"success": False, "detail": "Không có công việc nào được chọn."}, status_code=400)

        now = datetime.now(VN_TZ)
        deleter_id = user_session.get("id")

        # Thực hiện cập nhật hàng loạt
        updated_count = db.query(Task).filter(Task.id.in_(task_ids)).update({
            "status": "Đã xoá",
            "deleter_id": deleter_id,
            "deleted_at": now
        }, synchronize_session=False)

        db.commit()

        # Lấy lại các công việc vừa được cập nhật để trả về cho frontend
        updated_tasks = db.query(Task).options(
            joinedload(Task.branch),
            joinedload(Task.author),
            joinedload(Task.assignee),
            joinedload(Task.deleter)
        ).filter(Task.id.in_(task_ids)).all()

        return JSONResponse({"success": True, "updated_count": updated_count, "tasks": [task_to_dict(t) for t in updated_tasks]})
    except Exception as e:
        db.rollback()
        logger.error(f"Lỗi khi xóa mềm công việc hàng loạt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lỗi server: {str(e)}")

@router.get("/api/tasks/calendar-events")
def get_calendar_tasks(
    request: Request,
    start: date, # FastAPI sẽ tự động parse YYYY-MM-DD
    end: date,
    db: Session = Depends(get_db)
):
    user_data = request.session.get("user")
    if not user_data:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Lấy chi nhánh hoạt động để lọc (quan trọng cho lễ tân)
    active_branch = get_active_branch(request, db, user_data)
    branch_to_filter = ""
    if user_data.get("role") == 'letan':
        branch_to_filter = active_branch

    # Dùng lại hàm filter nhưng chỉ lấy các task trong khoảng thời gian
    tasks_query = _get_filtered_tasks_query(db, user_data, chi_nhanh=branch_to_filter)

    # Thêm điều kiện lọc theo ngày
    tasks_in_range = tasks_query.filter(
        Task.due_date >= start,
        Task.due_date < end
    ).all()

    # Chuyển đổi sang định dạng mà FullCalendar mong đợi
    events = []
    for task in tasks_in_range:
        events.append({
            "id": task.id,
            "title": task.description,
            "start": task.due_date.isoformat(),
            "id_task": task.id_task, # Thêm ID công việc vào đây
            "extendedProps": {
                # SỬA LỖI: Thay vì dùng TaskSchema, tạo một dictionary đầy đủ thông tin đã được định dạng
                # để khớp với cấu trúc mà hàm showTaskDetail() mong đợi.
                "phong": task.room_number,
                "trang_thai": task.status,
                "task_data": {
                    "id": task.id,
                    "id_task": task.id_task,
                    "chi_nhanh": task.branch.branch_code if task.branch else "N/A",
                    "phong": task.room_number,
                    "mo_ta": task.description,
                    "department": task.department or "Chưa gán",
                    "ngay_tao": format_datetime_display(task.created_at, with_time=True),
                    "han_hoan_thanh": format_datetime_display(task.due_date, with_time=True),
                    "han_hoan_thanh_raw": task.due_date.isoformat() if task.due_date else None,
                    "trang_thai": task.status,
                    "nguoi_tao": f"{task.author.name} ({task.author.employee_code})" if task.author else "N/A",
                    "ghi_chu": task.notes or "",
                    "nguoi_thuc_hien": task.assignee.name if task.assignee else "",
                    "ngay_hoan_thanh": format_datetime_display(task.completed_at, with_time=True) if task.completed_at else "",
                    "nguoi_xoa": task.deleter.name if task.deleter else "",
                    "ngay_xoa": format_datetime_display(task.deleted_at, with_time=True) if task.deleted_at else "",
                }
            }
        })
    return JSONResponse(content=events)

@router.post("/edit/{task_id}")
async def edit_submit(
    request: Request,
    task_id: int,
    db: Session = Depends(get_db),
    chi_nhanh: Optional[str] = Form(None), # branch_code
    vi_tri: str = Form(..., alias="phong"), # Đổi tên biến, giữ alias để form cũ hoạt động
    mo_ta: str = Form(...),
    bo_phan: str = Form(...),
    han_hoan_thanh: str = Form(...),
    ghi_chu: str = Form(""),
):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse("/login", status_code=303)
    
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Không tìm thấy công việc")

    # Lấy đối tượng Chi nhánh từ DB
    branch = db.query(Branch).filter(Branch.branch_code == chi_nhanh).first()
    if not branch:
        raise HTTPException(status_code=400, detail="Chi nhánh không hợp lệ")

    # Sửa logic: Chuyển đổi ngày từ form và kết hợp với giờ hiện tại, giống như khi thêm mới.
    # Điều này cho phép input chỉ cần là ngày (YYYY-MM-DD).
    due_date_only = datetime.strptime(han_hoan_thanh, "%Y-%m-%d").date()
    now_time = datetime.now(VN_TZ).time()
    han = VN_TZ.localize(datetime.combine(due_date_only, now_time))


    now = datetime.now(VN_TZ)

    # Cập nhật các cột mới
    task.branch_id = branch.id
    task.room_number = vi_tri
    task.description = mo_ta
    task.department = bo_phan
    task.due_date = han
    task.notes = ghi_chu
    
    # Sửa lỗi: Kiểm tra 'han' trước khi so sánh để tránh TypeError
    if han:
        task.status = "Quá hạn" if han < now else "Đang chờ"
    else:
        task.status = "Đang chờ" # Nếu không có hạn, mặc định là đang chờ

    db.commit()
    db.refresh(task)

    if request.query_params.get("json") == "1":
        return JSONResponse({"success": True, "task": task_to_dict(task)})

    # Lấy query_string để redirect giữ lại filter
    form_data = await request.form()
    redirect_query = form_data.get("redirect_query", "")

    return RedirectResponse(f"/tasks?success=1&action=update{('&' + redirect_query) if redirect_query else ''}", status_code=303)