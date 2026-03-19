from fastapi import APIRouter
from datetime import datetime
router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok", "app": "FormIntellect", "version": "1.0.0", "time": datetime.now().isoformat()}
