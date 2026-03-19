from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from engine.distributor import (
    apply_preset, generate_batch, save_config,
    load_config, list_configs, normalize_weights, weights_to_counts,
)
from engine.submitter import build_form_url, submit_row
from engine.metadata  import fetch_form_metadata
from engine.scheduler import validate_time_window, build_offsets, seconds_until, format_human

import threading, time, pytz
from datetime import datetime

router = APIRouter()
IST    = pytz.timezone("Asia/Kolkata")

_gen_state = {
    "status": "idle", "total": 0, "submitted": 0,
    "failed": 0, "current_row": 0, "log": [],
    "stop_requested": False,
}
_gen_lock   = threading.Lock()
_gen_thread = None


# ── Request models ────────────────────────────────────────────────────────────

class PresetRequest(BaseModel):
    options: list
    preset:  str = "uniform"


class PreviewRequest(BaseModel):
    dist_config:   dict
    total_rows:    int   = 5
    identity_rows: list  = []


class SaveConfigRequest(BaseModel):
    dist_config: dict
    name:        str


class GenerateStartRequest(BaseModel):
    prefilled_link: str
    dist_config:    dict
    total_rows:     int  = 10
    identity_rows:  list = []
    scheduler:      dict = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/generate/presets")
def get_presets():
    return {"presets": ["uniform", "bell", "skewed_left", "skewed_right", "realistic"]}


@router.post("/generate/apply-preset")
def apply_preset_route(req: PresetRequest):
    weights = apply_preset(req.options, req.preset)
    counts  = weights_to_counts(weights, 100)
    return {"options": req.options, "weights": weights, "counts": counts, "preset": req.preset}


@router.post("/generate/preview")
def generate_preview(req: PreviewRequest):
    if not req.dist_config:
        return {"success": False, "error": "dist_config is required."}
    identity_rows = req.identity_rows or [{}] * req.total_rows
    if len(identity_rows) < req.total_rows:
        identity_rows += [{}] * (req.total_rows - len(identity_rows))
    rows = generate_batch(req.dist_config, identity_rows[:req.total_rows])
    return {"success": True, "rows": rows, "total": len(rows)}


@router.post("/generate/save-config")
def save_config_route(req: SaveConfigRequest):
    try:
        path = save_config(req.dist_config, req.name)
        return {"success": True, "path": path, "name": req.name}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/generate/list-configs")
def list_configs_route():
    return {"configs": list_configs()}


@router.get("/generate/load-config/{name}")
def load_config_route(name: str):
    try:
        cfg = load_config(name)
        return {"success": True, "dist_config": cfg, "name": name}
    except FileNotFoundError as e:
        return {"success": False, "error": str(e)}


@router.post("/generate/start")
def generate_start(req: GenerateStartRequest):
    global _gen_thread
    with _gen_lock:
        if _gen_state["status"] == "running":
            return {"success": False, "error": "Generation already running."}

    identity_rows = req.identity_rows or [{}] * req.total_rows
    if len(identity_rows) < req.total_rows:
        identity_rows += [{}] * (req.total_rows - len(identity_rows))

    rows = generate_batch(req.dist_config, identity_rows[:req.total_rows])

    sched = req.scheduler
    window = validate_time_window(
        start_input    = sched.get("start_time", "00:00"),
        end_input      = sched.get("end_time",   "23:59"),
        start_rand_min = sched.get("start_rand_min", 0),
        start_rand_max = sched.get("start_rand_max", 60),
        end_rand_min   = sched.get("end_rand_min",   60),
        end_rand_max   = sched.get("end_rand_max",   300),
        total_rows     = len(rows),
    )
    if not window["ok"]:
        return {"success": False, "error": window["error"]}

    meta        = fetch_form_metadata(req.prefilled_link)
    field_types = meta.get("field_types", {})
    form_url    = build_form_url(req.prefilled_link)
    offsets     = build_offsets(window["window_sec"], len(rows))

    all_entry_cols   = [c for c in (rows[0].keys() if rows else []) if c.startswith("entry.")]
    required_columns = {c: c for c in all_entry_cols}

    with _gen_lock:
        _gen_state.update({
            "status": "running", "total": len(rows), "submitted": 0,
            "failed": 0, "current_row": 0, "log": [], "stop_requested": False,
        })

    _gen_thread = threading.Thread(
        target=_gen_drip_loop,
        args=(rows, required_columns, field_types, form_url,
              req.prefilled_link, offsets, window["rand_start"]),
        daemon=True,
    )
    _gen_thread.start()

    return {
        "success": True, "total": len(rows),
        "window_sec": window["window_sec"],
        "rand_start_fmt": window["rand_start_fmt"],
        "rand_end_fmt":   window["rand_end_fmt"],
    }


@router.get("/generate/status")
def generate_status():
    with _gen_lock:
        return dict(_gen_state)


@router.post("/generate/stop")
def generate_stop():
    with _gen_lock:
        _gen_state["stop_requested"] = True
        _gen_state["status"]         = "stopped"
    return {"success": True, "message": "Stop requested."}


# ── Drip loop ─────────────────────────────────────────────────────────────────

def _gen_drip_loop(rows, required_columns, field_types, form_url,
                   prefilled_link, offsets, rand_start_iso):
    start_ref = datetime.now(IST)
    wait_sec  = seconds_until(rand_start_iso)
    if wait_sec > 0:
        _gen_log(f"Waiting {format_human(int(wait_sec))} until start...")
        _gen_sleep(wait_sec)
    total = len(rows)
    for i, (row, offset) in enumerate(zip(rows, offsets)):
        with _gen_lock:
            if _gen_state["stop_requested"]:
                _gen_log("Stopped."); break
        target = start_ref.timestamp() + offset
        now    = datetime.now(IST).timestamp()
        if target > now:
            _gen_sleep(target - now)
        with _gen_lock:
            _gen_state["current_row"] = i + 1
        result  = submit_row(row, required_columns, field_types, form_url, prefilled_link)
        ist_now = datetime.now(IST).strftime("%H:%M:%S")
        with _gen_lock:
            if result["success"]:
                _gen_state["submitted"] += 1
                gap = offsets[i+1] - offsets[i] if i+1 < total else 0
                msg = f"Row {i+1} submitted at {ist_now} | " + (f"Next in {format_human(gap)}" if i+1 < total else "Final")
                _gen_log(msg, "success")
            else:
                _gen_state["failed"] += 1
                _gen_log(f"Row {i+1} FAILED | {result['reason']}", "error")
    with _gen_lock:
        if _gen_state["status"] != "stopped":
            _gen_state["status"] = "done"
        _gen_log("Complete.")


def _gen_log(message, level="info"):
    entry = {"time": datetime.now(IST).strftime("%H:%M:%S"), "message": message, "level": level}
    _gen_state["log"].append(entry)
    if len(_gen_state["log"]) > 500:
        _gen_state["log"] = _gen_state["log"][-500:]


def _gen_sleep(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        with _gen_lock:
            if _gen_state["stop_requested"]: return
        time.sleep(min(1.0, deadline - time.time()))
