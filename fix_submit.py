import os

os.makedirs('engine', exist_ok=True)
os.makedirs('server/routes', exist_ok=True)

files = {}

files['engine/scheduler.py'] = '''import random
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")
MIN_SECONDS_PER_ROW = 2


def validate_time_window(start_input, end_input, start_rand_min, start_rand_max,
                         end_rand_min, end_rand_max, total_rows, date_str=None):
    min_required = total_rows * MIN_SECONDS_PER_ROW
    if start_rand_min > start_rand_max:
        start_rand_min, start_rand_max = start_rand_max, start_rand_min
    if end_rand_min > end_rand_max:
        end_rand_min, end_rand_max = end_rand_max, end_rand_min
    today = date_str or datetime.now(IST).strftime("%Y-%m-%d")
    try:
        start_dt = IST.localize(datetime.strptime(f"{today} {start_input}", "%Y-%m-%d %H:%M"))
        end_dt   = IST.localize(datetime.strptime(f"{today} {end_input}",   "%Y-%m-%d %H:%M"))
    except ValueError:
        return {"ok": False, "error": "Invalid time format. Use HH:MM (e.g. 09:30)"}
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)
    original_window_sec = int((end_dt - start_dt).total_seconds())
    for _ in range(1000):
        rs  = random.randint(start_rand_min, start_rand_max)
        re_ = random.randint(end_rand_min,   end_rand_max)
        rand_start = start_dt + timedelta(seconds=rs)
        rand_end   = end_dt   + timedelta(seconds=re_)
        if rand_end <= rand_start:
            rand_end = rand_start + timedelta(seconds=1)
        window_sec = int((rand_end - rand_start).total_seconds())
        if window_sec > original_window_sec and window_sec >= min_required:
            return {
                "ok": True, "error": None,
                "rand_start": rand_start.isoformat(),
                "rand_end":   rand_end.isoformat(),
                "rand_start_fmt": rand_start.strftime("%d-%m-%Y %H:%M:%S IST"),
                "rand_end_fmt":   rand_end.strftime("%d-%m-%Y %H:%M:%S IST"),
                "original_window_sec": original_window_sec,
                "window_sec": window_sec,
                "rs": rs, "re": re_,
                "min_required_sec": min_required,
            }
    return {"ok": False, "error": (
        f"Could not find valid randomization after 1000 attempts. "
        f"Final window must be > {original_window_sec}s AND >= {min_required}s. "
        f"Increase end_rand_max or widen your base time window."
    )}


def build_offsets(window_sec, total_rows):
    safe_window = max(window_sec, total_rows * MIN_SECONDS_PER_ROW + 5)
    if total_rows > safe_window:
        step = safe_window / total_rows
        return [int(i * step) + 1 for i in range(total_rows)]
    return sorted(random.sample(range(1, safe_window + 1), total_rows))


def seconds_until(target_iso):
    target = datetime.fromisoformat(target_iso)
    if target.tzinfo is None:
        target = IST.localize(target)
    return max(0.0, (target - datetime.now(IST)).total_seconds())


def format_human(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def format_mm_ss(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"
'''

files['engine/submitter.py'] = '''import time
import requests
from engine.validator import normalize_value

MAX_RETRIES   = 3
RETRY_BACKOFF = 2


def build_form_url(prefilled_link):
    return prefilled_link.split("/viewform")[0] + "/formResponse"


def submit_row(row, required_columns, field_types, form_url, prefilled_link, max_retries=MAX_RETRIES):
    payload = {}
    for col, entry in required_columns.items():
        etype = field_types.get(entry, "text")
        value = normalize_value(row.get(col, ""), etype)
        if "," in value:
            payload[entry] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            payload[entry] = value
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":    prefilled_link,
        "Origin":     "https://docs.google.com",
    }
    session = requests.Session()
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(form_url, data=payload, headers=headers, timeout=30)
            if resp.status_code == 200 and (
                "Your response has been recorded" in resp.text or "formResponse" in resp.url
            ):
                return {"success": True,  "status_code": 200, "reason": "OK"}
            return {"success": False, "status_code": resp.status_code, "reason": f"HTTP {resp.status_code}"}
        except requests.exceptions.RequestException as exc:
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF * attempt)
            else:
                return {"success": False, "status_code": 0, "reason": str(exc)}
    return {"success": False, "status_code": 0, "reason": "Failed after max retries"}
'''

files['server/routes/submit.py'] = '''import threading, time
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
'''

for path, content in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  written  {path}")

print("\nDone. Restart server: python -m server.main")
