import threading, time
from datetime import datetime
from typing import Optional
import pytz
from fastapi import APIRouter
from pydantic import BaseModel
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from engine.scheduler import validate_time_window, build_offsets, seconds_until, format_human
from engine.submitter  import build_form_url, submit_row
from engine.metadata   import fetch_form_metadata

router = APIRouter()
IST    = pytz.timezone("Asia/Kolkata")

_state = {
    "status": "idle", "total": 0, "submitted": 0, "failed": 0,
    "current_row": 0, "log": [], "paused": False, "stop_requested": False,
}
_lock   = threading.Lock()
_thread: Optional[threading.Thread] = None


class SchedulerConfig(BaseModel):
    start_time:     str
    end_time:       str
    start_rand_min: int = 0
    start_rand_max: int = 60
    end_rand_min:   int = 0
    end_rand_max:   int = 120


class SubmitStartRequest(BaseModel):
    prefilled_link:   str
    rows:             list
    required_columns: dict
    scheduler:        SchedulerConfig


@router.post("/submit/validate-schedule")
def validate_schedule(req: SchedulerConfig, total_rows: int = 1):
    return validate_time_window(
        start_input=req.start_time, end_input=req.end_time,
        start_rand_min=req.start_rand_min, start_rand_max=req.start_rand_max,
        end_rand_min=req.end_rand_min,     end_rand_max=req.end_rand_max,
        total_rows=total_rows,
    )


@router.post("/submit/start")
def submit_start(req: SubmitStartRequest):
    global _thread
    with _lock:
        if _state["status"] == "running":
            return {"success": False, "error": "A submission is already running."}
    window = validate_time_window(
        start_input=req.scheduler.start_time, end_input=req.scheduler.end_time,
        start_rand_min=req.scheduler.start_rand_min, start_rand_max=req.scheduler.start_rand_max,
        end_rand_min=req.scheduler.end_rand_min,     end_rand_max=req.scheduler.end_rand_max,
        total_rows=len(req.rows),
    )
    if not window["ok"]:
        return {"success": False, "error": window["error"]}
    meta        = fetch_form_metadata(req.prefilled_link)
    field_types = meta.get("field_types", {})
    form_url    = build_form_url(req.prefilled_link)
    offsets     = build_offsets(window["window_sec"], len(req.rows))
    with _lock:
        _state.update({"status": "running", "total": len(req.rows), "submitted": 0,
                       "failed": 0, "current_row": 0, "log": [],
                       "paused": False, "stop_requested": False})
    _thread = threading.Thread(
        target=_drip_loop,
        args=(req.rows, req.required_columns, field_types, form_url, req.prefilled_link,
              offsets, window["rand_start"]),
        daemon=True,
    )
    _thread.start()
    return {"success": True, "total": len(req.rows), "window_sec": window["window_sec"],
            "rand_start_fmt": window["rand_start_fmt"], "rand_end_fmt": window["rand_end_fmt"]}


@router.post("/submit/pause")
def submit_pause():
    with _lock:
        if _state["status"] != "running":
            return {"success": False, "error": "Not currently running."}
        _state["paused"] = True
        _state["status"] = "paused"
    return {"success": True, "message": "Paused."}


@router.post("/submit/resume")
def submit_resume():
    with _lock:
        if _state["status"] != "paused":
            return {"success": False, "error": "Not currently paused."}
        _state["paused"] = False
        _state["status"] = "running"
    return {"success": True, "message": "Resumed."}


@router.post("/submit/stop")
def submit_stop():
    with _lock:
        _state["stop_requested"] = True
        _state["status"]         = "stopped"
    return {"success": True, "message": "Stop requested."}


@router.get("/submit/status")
def submit_status():
    with _lock:
        return dict(_state)


def _drip_loop(rows, required_columns, field_types, form_url, prefilled_link, offsets, rand_start_iso):
    start_ref = datetime.now(IST)
    wait_sec  = seconds_until(rand_start_iso)
    if wait_sec > 0:
        _log(f"Waiting {format_human(int(wait_sec))} until start time...")
        _sleep_interruptible(wait_sec)
    total = len(rows)
    for i, (row, offset) in enumerate(zip(rows, offsets)):
        with _lock:
            if _state["stop_requested"]:
                _log("Stopped by user."); break
        while True:
            with _lock:
                p = _state["paused"]
            if not p: break
            time.sleep(1)
        target = start_ref.timestamp() + offset
        now    = datetime.now(IST).timestamp()
        if target > now:
            _sleep_interruptible(target - now)
        with _lock:
            _state["current_row"] = i + 1
        result  = submit_row(row, required_columns, field_types, form_url, prefilled_link)
        ist_now = datetime.now(IST).strftime("%H:%M:%S")
        with _lock:
            if result["success"]:
                _state["submitted"] += 1
                gap = offsets[i+1] - offsets[i] if i+1 < total else 0
                msg = f"Row {i+1} submitted at {ist_now} | " + (f"Next in {format_human(gap)}" if i+1 < total else "Final entry")
                _log(msg, "success")
            else:
                _state["failed"] += 1
                _log(f"Row {i+1} FAILED at {ist_now} | {result['reason']}", "error")
    with _lock:
        if _state["status"] not in ("stopped",):
            _state["status"] = "done"
        _log("Process complete.")


def _log(message, level="info"):
    entry = {"time": datetime.now(IST).strftime("%H:%M:%S"), "message": message, "level": level}
    _state["log"].append(entry)
    if len(_state["log"]) > 500:
        _state["log"] = _state["log"][-500:]


def _sleep_interruptible(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        with _lock:
            if _state["stop_requested"]: return
        time.sleep(min(1.0, deadline - time.time()))
