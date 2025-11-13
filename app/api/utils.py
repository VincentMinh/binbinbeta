import os
from datetime import datetime, date
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..core.utils import VN_TZ
from ..core.config import logger
from ..services.missing_attendance_service import run_daily_absence_check

router = APIRouter(tags=["Utilities"])

@router.get("/ping")
async def ping():
    """
    Endpoint để kiểm tra "sức khỏe" của ứng dụng, hữu ích cho các dịch vụ giám sát.
    """
    return {"status": "ok", "timestamp": datetime.now(VN_TZ).isoformat()}

class AbsenceCheckRequest(BaseModel):
    check_date: date

@router.post("/api/attendance/run-absence-check")
async def trigger_absence_check(
    request: Request,
    payload: AbsenceCheckRequest,
    db: Session = Depends(get_db)
):
    """
    Endpoint để admin/boss có thể kích hoạt lại tác vụ kiểm tra vắng mặt cho một ngày cụ thể.
    """
    user_session = request.session.get("user")
    if not user_session or user_session.get("role") not in ["admin", "boss"]:
        raise HTTPException(status_code=403, detail="Bạn không có quyền thực hiện hành động này.")

    target_date = payload.check_date
    if not target_date:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp ngày cần kiểm tra.")

    try:
        run_daily_absence_check(target_date=target_date)
        logger.info(f"Admin '{user_session.get('code')}' đã kích hoạt kiểm tra vắng mặt cho ngày {target_date}.")
        return JSONResponse(content={"status": "success", "message": f"Đã gửi yêu cầu chạy kiểm tra vắng mặt cho ngày {target_date.strftime('%d/%m/%Y')}."})
    except Exception as e:
        logger.error(f"Lỗi khi admin kích hoạt kiểm tra vắng mặt: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Đã xảy ra lỗi khi xử lý yêu cầu: {str(e)}")

@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Trả về file favicon.ico hoặc một ảnh PNG mặc định."""
    favicon_path = os.path.join("app/static", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    # Trả về 1x1 PNG trong suốt nếu không có file
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\xdac\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\x0b\x0c\x00\x00\x00\x00IEND\xaeB`\x82'
    return Response(content=png_data, media_type="image/png")