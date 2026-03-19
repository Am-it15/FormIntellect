import os, json

os.makedirs('engine', exist_ok=True)
os.makedirs('server/routes', exist_ok=True)
os.makedirs('configs', exist_ok=True)

files = {}

# ── engine/distributor.py ─────────────────────────────────────────────────────
files['engine/distributor.py'] = '''import random
import json
import os

CONFIGS_DIR = "configs"


# ── Presets ───────────────────────────────────────────────────────────────────

def apply_preset(options: list, preset: str) -> list:
    """
    Return weights list for given preset name.
    Presets: uniform | bell | skewed_left | skewed_right | realistic
    """
    n = len(options)
    if n == 0:
        return []

    if preset == "uniform":
        w = [100.0 / n] * n
        return w

    if preset == "bell":
        mid = (n - 1) / 2.0
        raw = [1.0 / (1 + abs(i - mid) * 1.2) for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    if preset == "skewed_right":
        raw = [n - i for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    if preset == "skewed_left":
        raw = [i + 1 for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    if preset == "realistic":
        if n == 1:
            return [100.0]
        if n == 2:
            return [60.0, 40.0]
        if n == 3:
            return [20.0, 50.0, 30.0]
        if n == 4:
            return [10.0, 40.0, 35.0, 15.0]
        if n == 5:
            return [5.0, 20.0, 45.0, 20.0, 10.0]
        mid = (n - 1) / 2.0
        raw = [1.0 / (1 + abs(i - mid) * 0.8) for i in range(n)]
        total = sum(raw)
        return [round(r / total * 100, 2) for r in raw]

    return [100.0 / n] * n


# ── Single response generator ─────────────────────────────────────────────────

def generate_response(dist_config: dict, identity_row: dict = None) -> dict:
    """
    Generate one synthetic response row from dist_config.
    dist_config: {entry_id: spec_dict}
    """
    row = dict(identity_row) if identity_row else {}

    for eid, spec in dist_config.items():
        stype = spec.get("type", "")

        if stype in {"radio", "select", "scale", "grid"}:
            options = spec.get("options", [])
            weights = spec.get("weights", [])
            if options and weights:
                row[eid] = random.choices(options, weights=weights, k=1)[0]
            elif options:
                row[eid] = random.choice(options)
            else:
                row[eid] = ""

        elif stype == "checkbox":
            probs    = spec.get("probs", {})
            selected = [opt for opt, prob in probs.items() if random.random() < prob / 100.0]
            row[eid] = ", ".join(selected) if selected else ""

        elif stype in {"text", "textarea"}:
            mode = spec.get("mode", "blank")
            if mode == "pool":
                pool  = spec.get("pool", [])
                texts = [p[0] for p in pool]
                wts   = [p[1] for p in pool]
                row[eid] = random.choices(texts, weights=wts, k=1)[0] if pool else ""
            else:
                row[eid] = ""

        elif stype in {"date", "time", "datetime-local"}:
            row[eid] = spec.get("fixed", "")

        else:
            row[eid] = ""

    return row


def generate_batch(dist_config: dict, identity_rows: list) -> list:
    return [generate_response(dist_config, identity) for identity in identity_rows]


# ── Config save / load ────────────────────────────────────────────────────────

def save_config(dist_config: dict, name: str) -> str:
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = os.path.join(CONFIGS_DIR, f"{safe_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dist_config, f, indent=2)
    return path


def load_config(name: str) -> dict:
    path = os.path.join(CONFIGS_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_configs() -> list:
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    return [
        f[:-5] for f in os.listdir(CONFIGS_DIR)
        if f.endswith(".json") and f != ".gitkeep"
    ]


# ── Weight helpers ────────────────────────────────────────────────────────────

def normalize_weights(weights: list) -> list:
    total = sum(weights)
    if total == 0:
        return [100.0 / len(weights)] * len(weights)
    return [round(w / total * 100, 4) for w in weights]


def counts_to_weights(counts: list, total: int) -> list:
    if total == 0:
        return [100.0 / len(counts)] * len(counts)
    return [round(c / total * 100, 4) for c in counts]


def weights_to_counts(weights: list, total: int) -> list:
    return [round(w / 100.0 * total) for w in weights]
'''

# ── server/routes/generate.py ─────────────────────────────────────────────────
files['server/routes/generate.py'] = '''from fastapi import APIRouter
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
                _gen_log(f"Row {i+1} FAILED | {result[\'reason\']}", "error")
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
'''

# ── appsscript/DistributionModal.html ─────────────────────────────────────────
files['appsscript/DistributionModal.html'] = '''<!DOCTYPE html>
<html><head><base target="_top">
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:Arial,sans-serif}
body{font-size:13px;color:#202124;background:#fff;padding:16px}
h3{font-size:14px;font-weight:bold;color:#1F3864;margin-bottom:4px}
.subtitle{font-size:11px;color:#888;margin-bottom:14px}
.q-card{border:1px solid #e0e0e0;border-radius:6px;padding:12px;margin-bottom:12px}
.q-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.q-label{font-size:12px;font-weight:bold;color:#202124;flex:1}
.q-type{font-size:10px;padding:2px 7px;border-radius:3px;background:#E6F1FB;color:#0C447C}
.preset-row{display:flex;gap:5px;margin-bottom:10px;flex-wrap:wrap}
.preset-btn{font-size:10px;padding:3px 8px;border-radius:3px;border:1px solid #ccc;background:#fff;cursor:pointer;color:#555}
.preset-btn:hover{background:#f0f0f0}
.preset-btn.active{background:#1F3864;color:#fff;border-color:#1F3864}
.option-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.option-label{font-size:12px;color:#202124;flex:0 0 120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.option-slider{flex:1}
.option-pct{font-size:11px;font-weight:bold;color:#1F3864;min-width:36px;text-align:right}
.option-count{font-size:11px;color:#888;min-width:40px;text-align:right}
.total-row{display:flex;justify-content:space-between;font-size:11px;margin-top:6px;padding-top:6px;border-top:1px solid #eee}
.total-label{color:#888}
.total-val{font-weight:bold}
.total-val.ok{color:#1D9E75}
.total-val.err{color:#E24B4A}
.mode-row{display:flex;gap:8px;margin-bottom:8px}
.mode-btn{flex:1;padding:5px;border-radius:4px;border:1px solid #ccc;background:#fff;cursor:pointer;font-size:11px;color:#555;text-align:center}
.mode-btn.active{background:#1F3864;color:#fff;border-color:#1F3864}
.cb-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.cb-label{font-size:12px;flex:0 0 120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cb-slider{flex:1}
.cb-pct{font-size:11px;font-weight:bold;color:#1F3864;min-width:36px;text-align:right}
.divider{height:1px;background:#e0e0e0;margin:14px 0}
.preview-table{width:100%;border-collapse:collapse;font-size:11px;margin-top:8px}
.preview-table th{background:#f5f5f5;padding:5px 8px;text-align:left;border:1px solid #e0e0e0;font-weight:bold}
.preview-table td{padding:4px 8px;border:1px solid #e0e0e0;max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.status-row{display:flex;align-items:center;gap:6px;padding:7px 10px;border-radius:4px;font-size:12px;margin-top:8px}
.status-row.ok{background:#E1F5EE;color:#085041}
.status-row.err{background:#FCEBEB;color:#A32D2D}
.status-row.info{background:#E6F1FB;color:#0C447C}
.dot{width:6px;height:6px;border-radius:50%}
.dot-green{background:#1D9E75}.dot-red{background:#E24B4A}.dot-blue{background:#378ADD}
.btn-row{display:flex;gap:8px;margin-top:14px}
.btn{flex:1;padding:9px;border-radius:4px;font-size:12px;font-weight:bold;cursor:pointer;border:none}
.btn-primary{background:#1F3864;color:#fff}
.btn-primary:hover{background:#162848}
.btn-primary:disabled{background:#ccc;cursor:not-allowed}
.btn-ghost{background:#fff;color:#555;border:1px solid #ccc}
.btn-ghost:hover{background:#f5f5f5}
.btn-sm{padding:5px 10px;font-size:11px;border-radius:4px;border:1px solid #ccc;background:#fff;cursor:pointer}
.btn-sm:hover{background:#f5f5f5}
.save-row{display:flex;gap:6px;margin-top:8px}
.save-row input{flex:1;padding:6px 8px;font-size:12px;border:1px solid #ccc;border-radius:4px}
.spinner{display:inline-block;width:11px;height:11px;border:2px solid #ccc;border-top-color:#1F3864;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:5px}
@keyframes spin{to{transform:rotate(360deg)}}
input[type=range]{width:100%;accent-color:#1F3864}
select{padding:5px 8px;font-size:12px;border:1px solid #ccc;border-radius:4px;outline:none}
</style>
</head><body>

<h3>Distribution config</h3>
<div class="subtitle" id="formTitle">Loading form questions...</div>

<div id="questionsContainer"></div>

<div class="divider"></div>

<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
  <div style="font-size:12px;font-weight:bold;color:#555">Preview</div>
  <div style="display:flex;gap:6px;align-items:center">
    <span style="font-size:11px;color:#888">Rows:</span>
    <select id="previewCount" style="width:60px">
      <option>3</option><option selected>5</option><option>10</option>
    </select>
    <button class="btn-sm" onclick="runPreview()">Generate</button>
  </div>
</div>
<div id="previewArea"><div style="font-size:11px;color:#888">Click Generate to preview rows.</div></div>

<div class="divider"></div>

<div style="font-size:12px;font-weight:bold;color:#555;margin-bottom:6px">Save config</div>
<div class="save-row">
  <input type="text" id="configName" placeholder="Config name (e.g. survey_jan)"/>
  <button class="btn-sm" onclick="saveConfig()">Save</button>
  <select id="savedConfigs" onchange="loadConfig(this.value)" style="max-width:120px">
    <option value="">Load saved...</option>
  </select>
</div>
<div id="saveMsg"></div>

<div class="btn-row">
  <button class="btn btn-ghost" onclick="google.script.host.close()">Cancel</button>
  <button class="btn btn-primary" id="btnConfirm" onclick="confirmConfig()">Confirm →</button>
</div>

<script>
var questions    = [];
var distConfig   = {};
var totalRows    = 10;
var displayMode  = "pct";   // pct | count

window.onload = function() {
  google.script.run
    .withSuccessHandler(function(data) {
      questions = data.questions || [];
      totalRows = data.totalRows || 10;
      document.getElementById("formTitle").textContent =
        (data.formTitle || "Form") + " — " + questions.length + " questions";
      buildQuestions();
      loadSavedConfigs();
    })
    .withFailureHandler(function(e) {
      document.getElementById("formTitle").textContent = "Error: " + e.message;
    })
    .getDistributionData();
};

function buildQuestions() {
  var container = document.getElementById("questionsContainer");
  container.innerHTML = "";
  questions.forEach(function(q, qi) {
    var options = q.options || [];
    var ftype   = q.type;
    var div     = document.createElement("div");
    div.className = "q-card";
    div.id = "qcard_" + qi;

    var header = \'<div class="q-header"><span class="q-label">\' + (q.label || q.entry_id) +
      \'</span><span class="q-type">\' + ftype + \'</span></div>\';

    if (["radio","select","scale"].includes(ftype) && options.length) {
      distConfig[q.entry_id] = distConfig[q.entry_id] || {
        type: ftype, options: options,
        weights: options.map(function() { return Math.round(100/options.length * 10)/10; })
      };
      div.innerHTML = header + buildSliderBlock(q.entry_id, options, qi);
    } else if (ftype === "checkbox" && options.length) {
      distConfig[q.entry_id] = distConfig[q.entry_id] || {
        type: "checkbox",
        probs: Object.fromEntries(options.map(function(o) { return [o, 50]; }))
      };
      div.innerHTML = header + buildCheckboxBlock(q.entry_id, options, qi);
    } else if (ftype === "grid") {
      div.innerHTML = header + \'<div style="font-size:11px;color:#888">Grid field — auto-handled per sub-question.</div>\';
    } else {
      div.innerHTML = header + \'<div style="font-size:11px;color:#888">Text field — will submit empty.</div>\';
      distConfig[q.entry_id] = { type: ftype, mode: "blank" };
    }
    container.appendChild(div);
  });
}

function buildSliderBlock(eid, options, qi) {
  var html = \'<div class="preset-row">\';
  ["uniform","bell","skewed_left","skewed_right","realistic"].forEach(function(p) {
    html += \'<button class="preset-btn" onclick="applyPreset(\\\'\' + eid + \'\\\',\\\'\' + p + \'\\\',\' + qi + \')">\'
      + p.replace("_"," ") + \'</button>\';
  });
  html += \'</div>\';
  var weights = distConfig[eid].weights;
  options.forEach(function(opt, i) {
    var w = Math.round((weights[i] || 0) * 10) / 10;
    var c = Math.round(w / 100 * totalRows);
    html += \'<div class="option-row">\' +
      \'<span class="option-label" title="\' + opt + \'">\' + opt + \'</span>\' +
      \'<input type="range" class="option-slider" min="0" max="100" step="1" value="\' + w +
      \'" oninput="onSlider(\\\'\' + eid + \'\\\',\' + i + \',this.value,\' + qi + \')" />\' +
      \'<span class="option-pct" id="pct_\' + eid + \'_\' + i + \'">\' + w + \'%</span>\' +
      \'<span class="option-count" id="cnt_\' + eid + \'_\' + i + \'">\' + c + \'</span>\' +
      \'</div>\';
  });
  var total = weights.reduce(function(a,b){return a+b;},0);
  html += \'<div class="total-row"><span class="total-label">Total</span>\' +
    \'<span class="total-val \' + (Math.abs(total-100)<1?"ok":"err") + \'" id="total_\' + eid + \'">\' +
    Math.round(total) + \'%</span></div>\';
  return html;
}

function buildCheckboxBlock(eid, options, qi) {
  var probs = distConfig[eid].probs;
  var html  = \'<div style="font-size:11px;color:#888;margin-bottom:6px">Independent selection probability per option</div>\';
  options.forEach(function(opt, i) {
    var p = probs[opt] !== undefined ? probs[opt] : 50;
    html += \'<div class="cb-row">\' +
      \'<span class="cb-label" title="\' + opt + \'">\' + opt + \'</span>\' +
      \'<input type="range" class="cb-slider" min="0" max="100" step="1" value="\' + p +
      \'" oninput="onCbSlider(\\\'\' + eid + \'\\\',\\\'\' + opt + \'\\\',this.value)" />\' +
      \'<span class="cb-pct" id="cbpct_\' + eid + \'_\' + i + \'">\' + p + \'%</span>\' +
      \'</div>\';
  });
  return html;
}

function onSlider(eid, idx, val, qi) {
  distConfig[eid].weights[idx] = parseFloat(val);
  var weights = distConfig[eid].weights;
  var options = distConfig[eid].options;
  options.forEach(function(_, i) {
    var w = Math.round((weights[i]||0)*10)/10;
    var c = Math.round(w/100*totalRows);
    var pe = document.getElementById("pct_"+eid+"_"+i);
    var ce = document.getElementById("cnt_"+eid+"_"+i);
    if(pe) pe.textContent = w + "%";
    if(ce) ce.textContent = c;
  });
  var total = weights.reduce(function(a,b){return a+b;},0);
  var te = document.getElementById("total_"+eid);
  if(te){ te.textContent = Math.round(total)+"%"; te.className="total-val "+(Math.abs(total-100)<1?"ok":"err"); }
}

function onCbSlider(eid, opt, val) {
  distConfig[eid].probs[opt] = parseFloat(val);
  var options = distConfig[eid].options || Object.keys(distConfig[eid].probs);
  var idx = options.indexOf(opt);
  var el  = document.getElementById("cbpct_"+eid+"_"+idx);
  if(el) el.textContent = val+"%";
}

function applyPreset(eid, preset, qi) {
  var options = distConfig[eid].options;
  google.script.run
    .withSuccessHandler(function(res) {
      distConfig[eid].weights = res.weights;
      var card = document.getElementById("qcard_"+qi);
      if(card) {
        var header = card.querySelector(".q-header").outerHTML;
        card.innerHTML = header + buildSliderBlock(eid, options, qi);
      }
      card.querySelectorAll(".preset-btn").forEach(function(b){
        b.classList.toggle("active", b.textContent.replace(" ","_")===preset);
      });
    })
    .applyPreset(options, preset);
}

function runPreview() {
  var n = parseInt(document.getElementById("previewCount").value) || 5;
  document.getElementById("previewArea").innerHTML =
    \'<div class="status-row info"><span class="spinner"></span>Generating preview...</div>\';
  google.script.run
    .withSuccessHandler(function(res) {
      if(!res.success){ document.getElementById("previewArea").innerHTML=\'<div class="status-row err"><div class="dot dot-red"></div>\'+res.error+\'</div>\'; return; }
      var rows = res.rows;
      if(!rows.length){ document.getElementById("previewArea").innerHTML=\'<div style="font-size:11px;color:#888">No rows generated.</div>\'; return; }
      var keys = Object.keys(rows[0]);
      var html = \'<div style="overflow-x:auto"><table class="preview-table"><thead><tr>\';
      keys.forEach(function(k){ html+=\'<th>\'+k+\'</th>\'; });
      html+=\'</tr></thead><tbody>\';
      rows.forEach(function(row){
        html+=\'<tr>\';
        keys.forEach(function(k){ html+=\'<td title="\'+String(row[k]||"")+\'">\'+String(row[k]||"")+\'</td>\'; });
        html+=\'</tr>\';
      });
      html+=\'</tbody></table></div>\';
      document.getElementById("previewArea").innerHTML=html;
    })
    .withFailureHandler(function(e){
      document.getElementById("previewArea").innerHTML=\'<div class="status-row err"><div class="dot dot-red"></div>\'+e.message+\'</div>\';
    })
    .previewDistribution(distConfig, n);
}

function saveConfig() {
  var name = document.getElementById("configName").value.trim();
  if(!name){ document.getElementById("saveMsg").innerHTML=\'<div style="font-size:11px;color:#E24B4A">Enter a config name.</div>\'; return; }
  google.script.run
    .withSuccessHandler(function(res){
      document.getElementById("saveMsg").innerHTML = res.success
        ? \'<div style="font-size:11px;color:#1D9E75">Saved: \'+res.name+\'</div>\'
        : \'<div style="font-size:11px;color:#E24B4A">Error: \'+res.error+\'</div>\';
      loadSavedConfigs();
    })
    .saveDistConfig(distConfig, name);
}

function loadSavedConfigs() {
  google.script.run
    .withSuccessHandler(function(configs){
      var sel = document.getElementById("savedConfigs");
      sel.innerHTML = \'<option value="">Load saved...</option>\';
      configs.forEach(function(c){ var o=document.createElement("option"); o.value=o.textContent=c; sel.appendChild(o); });
    })
    .listDistConfigs();
}

function loadConfig(name) {
  if(!name) return;
  google.script.run
    .withSuccessHandler(function(res){
      if(!res.success){ alert("Error: "+res.error); return; }
      distConfig = res.dist_config;
      buildQuestions();
    })
    .loadDistConfig(name);
}

function confirmConfig() {
  google.script.run
    .withSuccessHandler(function(){ google.script.host.close(); })
    .setDistConfig(distConfig);
}
</script>
</body></html>
'''

for path, content in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  written  {path}")

print("\nAll Phase 3 files written.")
print("Now restart server: python -m server.main")
