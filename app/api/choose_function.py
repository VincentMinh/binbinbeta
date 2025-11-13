from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..core.security import require_checked_in_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/choose-function", response_class=HTMLResponse)
async def choose_function(request: Request, db: Session = Depends(get_db)):
    """
    Hiển thị trang chọn chức năng chính sau khi người dùng đã đăng nhập và điểm danh thành công.
    """
    if not require_checked_in_user(request): # This check also ensures user is in session
        return RedirectResponse("/login", status_code=303)

    # Nếu có flag after_checkin thì xóa để tránh dùng lại
    if request.session.get("after_checkin") == "choose_function":
        request.session.pop("after_checkin", None)

    response = templates.TemplateResponse(
        "choose_function.html", {"request": request, "user": request.session.get("user")}
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response