from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/healthz", include_in_schema=False)
def health_check():
    return JSONResponse({"status": "healthy"})
