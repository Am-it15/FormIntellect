from fastapi import APIRouter
from pydantic import BaseModel
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.metadata import fetch_form_metadata, build_column_mapping

router = APIRouter()

class DetectRequest(BaseModel):
    prefilled_link: str
    columns:        list = []
    status_col:     str  = "Status"

@router.post("/detect")
def detect(req: DetectRequest):
    meta = fetch_form_metadata(req.prefilled_link)
    if meta["error"]:
        return {"success": False, "error": meta["error"]}
    column_mapping, mapping_error = {}, None
    if req.columns:
        try:
            column_mapping = build_column_mapping(req.columns, req.prefilled_link, req.status_col)
        except ValueError as e:
            mapping_error = str(e)
    questions = [{"entry_id": eid, "label": label, "type": ftype} for eid, label, ftype in meta["questions_order"]]
    return {
        "success":        True,
        "form_title":     meta["form_title"],
        "field_types":    meta["field_types"],
        "options":        meta["options_by_entry"],
        "grid_info":      meta["grid_info"],
        "questions":      questions,
        "column_mapping": column_mapping,
        "mapping_error":  mapping_error,
    }
