from fastapi import APIRouter
from pydantic import BaseModel
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engine.analyzer import generate_analysis_sheet, analyze_dataframe
import pandas as pd

router = APIRouter()


class AnalyzeRequest(BaseModel):
    file_path:       str
    submitted_count: int = 0


class SummaryRequest(BaseModel):
    file_path: str


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    result = generate_analysis_sheet(req.file_path, req.submitted_count)
    return result


@router.post("/analyze/summary")
def analyze_summary(req: SummaryRequest):
    if not os.path.exists(req.file_path):
        return {"success": False, "error": f"File not found: {req.file_path}"}
    try:
        lower = req.file_path.lower()
        if lower.endswith(".xlsx") or lower.endswith(".xls"):
            df = pd.read_excel(req.file_path)
        elif lower.endswith(".csv"):
            df = pd.read_csv(req.file_path)
        else:
            return {"success": False, "error": "Unsupported file type. Use .xlsx or .csv"}
        summary = analyze_dataframe(df)
        return {"success": True, "summary": summary, "total_rows": len(df)}
    except Exception as e:
        return {"success": False, "error": str(e)}
