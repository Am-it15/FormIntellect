import os

os.makedirs('appsscript', exist_ok=True)
os.makedirs('server/routes', exist_ok=True)
os.makedirs('engine', exist_ok=True)
os.makedirs('configs', exist_ok=True)
os.makedirs('docs', exist_ok=True)

files = {}

# ── .gitignore ────────────────────────────────────────────────────────────────
files['.gitignore'] = """venv/
__pycache__/
*.py[cod]
.env
configs/*.json
.DS_Store
Thumbs.db
*.log
"""

# ── requirements.txt ──────────────────────────────────────────────────────────
files['requirements.txt'] = """fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
requests>=2.31.0
pandas>=2.0.0
openpyxl>=3.1.0
odfpy>=1.4.1
pytz>=2024.1
pydantic>=2.7.0
"""

# ── start.sh ──────────────────────────────────────────────────────────────────
files['start.sh'] = """#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [ -d "venv/bin" ]; then source venv/bin/activate
elif [ -d "venv/Scripts" ]; then source venv/Scripts/activate; fi
PYTHON=$(command -v python3 || command -v python)
if ! $PYTHON -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies..."
  $PYTHON -m pip install -r requirements.txt --quiet
fi
echo ""
echo "================================================"
echo "  FormIntellect Server"
echo "  Running at http://localhost:5000"
echo "  Press Ctrl+C to stop."
echo "================================================"
echo ""
$PYTHON -m server.main
"""

# ── appsscript/appsscript.json ────────────────────────────────────────────────
files['appsscript/appsscript.json'] = """{
  "timeZone": "Asia/Kolkata",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/script.container.ui",
    "https://www.googleapis.com/auth/script.external_request"
  ],
  "addOns": {
    "common": {
      "name": "FormIntellect",
      "logoUrl": "https://www.gstatic.com/images/icons/material/system/1x/extension_black_24dp.png"
    },
    "sheets": {
      "homepageTrigger": {
        "runFunction": "onHomepageTrigger"
      }
    }
  }
}
"""

# ── appsscript/Code.gs ────────────────────────────────────────────────────────
files['appsscript/Code.gs'] = """var SERVER_URL = "http://localhost:5000";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("FormIntellect")
    .addItem("Open", "openSidebar")
    .addSeparator()
    .addItem("Check server status", "checkServer")
    .addToUi();
}

function onHomepageTrigger() { openSidebar(); }

function openSidebar() {
  var html = HtmlService.createHtmlOutputFromFile("Sidebar")
    .setTitle("FormIntellect")
    .setWidth(320);
  SpreadsheetApp.getUi().showSidebar(html);
}

function getSheetNames() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheets().map(function(s) {
    return s.getName();
  });
}

function getSheetColumns(sheetName) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(sheetName);
  if (!sheet) return { error: "Sheet not found: " + sheetName };
  var lastCol = sheet.getLastColumn();
  if (lastCol === 0) return { columns: [], rowCount: 0, submittedCount: 0, pendingCount: 0 };
  var headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  var columns = headers.map(String).filter(function(h) { return h.trim() !== ""; });
  var lastRow = sheet.getLastRow();
  var rowCount = Math.max(0, lastRow - 1);
  var submittedCount = 0;
  var statusIdx = columns.findIndex(function(c) {
    return ["status","submit","submitted"].includes(c.trim().toLowerCase());
  });
  if (statusIdx >= 0 && lastRow > 1) {
    var statusVals = sheet.getRange(2, statusIdx + 1, lastRow - 1, 1).getValues();
    submittedCount = statusVals.filter(function(r) {
      return String(r[0]).toLowerCase() === "submitted";
    }).length;
  }
  return { columns: columns, rowCount: rowCount, submittedCount: submittedCount, pendingCount: rowCount - submittedCount };
}

function pingServer() {
  try {
    var resp = UrlFetchApp.fetch(SERVER_URL + "/api/health", { method: "get", muteHttpExceptions: true, deadline: 5 });
    if (resp.getResponseCode() === 200) {
      var data = JSON.parse(resp.getContentText());
      return { online: true, version: data.version || "1.0.0" };
    }
    return { online: false, error: "HTTP " + resp.getResponseCode() };
  } catch (e) { return { online: false, error: e.message }; }
}

function detectForm(prefilled_link, sheetName) {
  var sheetInfo = getSheetColumns(sheetName);
  if (sheetInfo.error) return { success: false, error: sheetInfo.error };
  var payload = JSON.stringify({ prefilled_link: prefilled_link, columns: sheetInfo.columns, status_col: "Status" });
  try {
    var resp = UrlFetchApp.fetch(SERVER_URL + "/api/detect", {
      method: "post", contentType: "application/json", payload: payload, muteHttpExceptions: true, deadline: 30
    });
    var result = JSON.parse(resp.getContentText());
    result.rowCount       = sheetInfo.rowCount;
    result.submittedCount = sheetInfo.submittedCount;
    result.pendingCount   = sheetInfo.pendingCount;
    return result;
  } catch (e) { return { success: false, error: "Server unreachable: " + e.message }; }
}

function checkServer() {
  var result = pingServer();
  var ui = SpreadsheetApp.getUi();
  if (result.online) {
    ui.alert("FormIntellect server is online (v" + result.version + ")");
  } else {
    ui.alert("Server offline. Run: python -m server.main\\n\\nError: " + result.error);
  }
}
"""

# ── appsscript/Sidebar.html ───────────────────────────────────────────────────
files['appsscript/Sidebar.html'] = """<!DOCTYPE html>
<html><head><base target="_top">
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:Arial,sans-serif}
body{font-size:13px;color:#202124;background:#fff}
.topbar{background:#1F3864;padding:10px 14px;display:flex;align-items:center;gap:8px}
.topbar-logo{width:20px;height:20px;background:#378ADD;border-radius:4px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;font-weight:bold}
.topbar-title{color:#fff;font-size:13px;font-weight:bold;flex:1}
.srv-dot{width:7px;height:7px;border-radius:50%;background:#888}
.srv-dot.online{background:#1D9E75}
.srv-label{font-size:10px;color:#B4B2A9}
.srv-label.online{color:#9FE1CB}
.step-bar{display:flex;padding:10px 14px;border-bottom:1px solid #e0e0e0;align-items:center}
.step{display:flex;flex-direction:column;align-items:center;gap:2px;flex:0 0 auto}
.step-num{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:bold;border:1px solid #ccc;color:#888;background:#fff}
.step-num.active{background:#1F3864;color:#fff;border-color:#1F3864}
.step-num.done{background:#1D9E75;color:#fff;border-color:#1D9E75}
.step-lbl{font-size:10px;color:#888}
.step-lbl.active{color:#1F3864;font-weight:bold}
.connector{flex:1;height:1px;background:#e0e0e0;margin:0 4px;margin-bottom:10px}
.connector.done{background:#1D9E75}
.body{padding:14px}
.field-label{font-size:11px;font-weight:bold;color:#555;margin-bottom:4px}
.field-group{margin-bottom:14px}
.field-hint{font-size:11px;color:#888;margin-top:3px}
select,input[type=text]{width:100%;padding:7px 9px;font-size:13px;border:1px solid #ccc;border-radius:4px;outline:none;color:#202124}
select:focus,input[type=text]:focus{border-color:#1F3864}
.status-row{display:flex;align-items:center;gap:6px;padding:7px 10px;border-radius:4px;font-size:12px;margin-top:6px}
.status-row.ok{background:#E1F5EE;color:#085041}
.status-row.err{background:#FCEBEB;color:#A32D2D}
.status-row.info{background:#E6F1FB;color:#0C447C}
.dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.dot-green{background:#1D9E75}
.dot-red{background:#E24B4A}
.dot-blue{background:#378ADD}
.btn{width:100%;padding:9px;border-radius:4px;font-size:13px;font-weight:bold;cursor:pointer;margin-top:10px;border:none}
.btn-primary{background:#1F3864;color:#fff}
.btn-primary:hover{background:#162848}
.btn-primary:disabled{background:#ccc;cursor:not-allowed}
.btn-ghost{background:#fff;color:#555;border:1px solid #ccc}
.btn-ghost:hover{background:#f5f5f5}
.stat-row{display:flex;gap:8px;margin-top:10px}
.stat-box{flex:1;background:#f5f5f5;border-radius:4px;padding:8px;text-align:center}
.stat-val{font-size:20px;font-weight:bold;color:#202124}
.stat-lbl{font-size:10px;color:#888;margin-top:1px}
.map-card{background:#f9f9f9;border:1px solid #e0e0e0;border-radius:4px;padding:8px;margin-top:8px}
.map-row{display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid #eee;font-size:11px}
.map-row:last-child{border-bottom:none}
.map-col{font-weight:bold;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.map-arr{color:#aaa}
.map-entry{color:#185FA5;font-family:monospace;font-size:10px;flex:1;overflow:hidden;text-overflow:ellipsis}
.map-badge{font-size:9px;padding:1px 5px;border-radius:3px;background:#E1F5EE;color:#085041;flex-shrink:0}
.map-badge.warn{background:#FAEEDA;color:#633806}
.module-card{border:1px solid #e0e0e0;border-radius:6px;padding:12px;cursor:pointer;margin-bottom:8px}
.module-card:hover{border-color:#1F3864}
.module-card.selected{border:2px solid #1F3864}
.module-title{font-size:13px;font-weight:bold;margin-bottom:3px}
.module-desc{font-size:11px;color:#666;margin-bottom:6px}
.tag{display:inline-block;font-size:10px;padding:2px 6px;border-radius:3px;margin-right:4px}
.tag-coral{background:#FAECE7;color:#712B13}
.tag-amber{background:#FAEEDA;color:#633806}
.tag-teal{background:#E1F5EE;color:#085041}
.screen{display:none}
.screen.active{display:block}
.spinner{display:inline-block;width:12px;height:12px;border:2px solid #ccc;border-top-color:#1F3864;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:6px}
@keyframes spin{to{transform:rotate(360deg)}}
.banner{background:#E6F1FB;border-radius:4px;padding:9px 11px;font-size:12px;color:#0C447C;margin-bottom:12px;line-height:1.5}
.divider{height:1px;background:#e0e0e0;margin:12px 0}
.warn-row{display:flex;align-items:center;gap:6px;padding:7px 10px;border-radius:4px;font-size:12px;background:#FCEBEB;color:#A32D2D;margin-top:8px}
</style>
</head><body>
<div class="topbar">
  <div class="topbar-logo">FI</div>
  <div class="topbar-title">FormIntellect</div>
  <div class="srv-dot" id="srvDot"></div>
  <div class="srv-label" id="srvLabel">checking...</div>
</div>
<div class="step-bar">
  <div class="step"><div class="step-num active" id="sn1">1</div><div class="step-lbl active" id="sl1">Setup</div></div>
  <div class="connector" id="con1"></div>
  <div class="step"><div class="step-num" id="sn2">2</div><div class="step-lbl" id="sl2">Detect</div></div>
  <div class="connector" id="con2"></div>
  <div class="step"><div class="step-num" id="sn3">3</div><div class="step-lbl" id="sl3">Module</div></div>
</div>
<div class="body">
  <div class="screen active" id="screen1">
    <div class="banner">Select the sheet with your response data, then paste your Google Form pre-filled link.</div>
    <div class="field-group">
      <div class="field-label">Sheet in this workbook</div>
      <select id="sheetSelect" onchange="onSheetChange()"><option value="">— loading... —</option></select>
      <div class="field-hint" id="sheetHint"></div>
    </div>
    <div class="field-group">
      <div class="field-label">Google Form pre-filled link</div>
      <input type="text" id="linkInput" placeholder="https://docs.google.com/forms/d/..." oninput="onLinkInput()"/>
      <div id="linkStatus"></div>
      <div class="field-hint">Open form → three dots menu → Get pre-filled link</div>
    </div>
    <button class="btn btn-primary" id="btnDetect" disabled onclick="goDetect()">Detect fields →</button>
  </div>
  <div class="screen" id="screen2">
    <div id="detectingState">
      <div class="status-row info"><span class="spinner"></span><span id="detectMsg">Connecting to server...</span></div>
    </div>
    <div id="detectResult" style="display:none">
      <div class="status-row ok"><div class="dot dot-green"></div><span id="detectOkMsg">Fields detected</span></div>
      <div class="stat-row">
        <div class="stat-box"><div class="stat-val" id="statPending">-</div><div class="stat-lbl">Pending</div></div>
        <div class="stat-box"><div class="stat-val" id="statFields">-</div><div class="stat-lbl">Fields</div></div>
        <div class="stat-box"><div class="stat-val" id="statDone">-</div><div class="stat-lbl">Done</div></div>
      </div>
      <div class="divider"></div>
      <div class="field-label">Column to field mapping</div>
      <div class="map-card" id="mapCard"></div>
      <div id="warnRow" class="warn-row" style="display:none"><div class="dot dot-red"></div><span id="warnMsg"></span></div>
      <button class="btn btn-primary" onclick="goModules()">Continue →</button>
      <button class="btn btn-ghost" onclick="goStep(1)">← Back</button>
    </div>
    <div id="detectError" style="display:none">
      <div class="status-row err"><div class="dot dot-red"></div><span id="detectErrMsg">Error</span></div>
      <button class="btn btn-ghost" style="margin-top:10px" onclick="goStep(1)">← Back</button>
    </div>
  </div>
  <div class="screen" id="screen3">
    <div class="field-label" style="margin-bottom:10px;color:#666">Choose a module to launch</div>
    <div class="module-card" id="mod-submit" onclick="selectModule('submit')">
      <div class="module-title">Module 1 — Submit from sheet</div>
      <div class="module-desc">Submit sheet rows to the form with scheduling, retry, and live progress.</div>
      <span class="tag tag-coral">Scheduler</span><span class="tag tag-coral">Auto-retry</span><span class="tag tag-coral">Live log</span>
    </div>
    <div class="module-card" id="mod-generate" onclick="selectModule('generate')">
      <div class="module-title">Module 2 — Generate by distribution</div>
      <div class="module-desc">Design response distributions with sliders and generate synthetic data.</div>
      <span class="tag tag-amber">Sliders</span><span class="tag tag-amber">Presets</span><span class="tag tag-amber">Dry run</span>
    </div>
    <div class="module-card" id="mod-analyze" onclick="selectModule('analyze')">
      <div class="module-title">Module 3 — Analytics</div>
      <div class="module-desc">Generate a full analysis sheet with charts from submitted response data.</div>
      <span class="tag tag-teal">Charts</span><span class="tag tag-teal">Frequency</span><span class="tag tag-teal">Export</span>
    </div>
    <button class="btn btn-primary" id="btnLaunch" disabled onclick="launchModule()">Launch module →</button>
    <button class="btn btn-ghost" onclick="goStep(2)">← Back</button>
  </div>
</div>
<script>
var currentStep=1,selectedModule=null,detectData=null;
window.onload=function(){loadSheets();pingServer()};
function pingServer(){
  google.script.run.withSuccessHandler(function(res){
    var d=document.getElementById('srvDot'),l=document.getElementById('srvLabel');
    if(res.online){d.className='srv-dot online';l.className='srv-label online';l.textContent='server online';}
    else{d.className='srv-dot';l.className='srv-label';l.textContent='server offline';}
  }).withFailureHandler(function(){}).pingServer();
}
function loadSheets(){
  google.script.run.withSuccessHandler(function(names){
    var sel=document.getElementById('sheetSelect');
    sel.innerHTML='<option value="">— choose a sheet —</option>';
    names.forEach(function(n){var o=document.createElement('option');o.value=o.textContent=n;sel.appendChild(o);});
  }).withFailureHandler(function(){}).getSheetNames();
}
function onSheetChange(){
  var v=document.getElementById('sheetSelect').value;
  document.getElementById('sheetHint').textContent=v?'Selected: '+v:'';
  checkReady();
}
function onLinkInput(){
  var v=document.getElementById('linkInput').value.trim();
  var el=document.getElementById('linkStatus');
  if(!v){el.innerHTML='';checkReady();return;}
  if(v.includes('docs.google.com/forms')&&v.includes('viewform'))
    el.innerHTML='<div class="status-row ok" style="margin-top:5px"><div class="dot dot-green"></div>Valid Google Form link</div>';
  else
    el.innerHTML='<div class="status-row err" style="margin-top:5px"><div class="dot dot-red"></div>Not a valid pre-filled link</div>';
  checkReady();
}
function checkReady(){
  var s=document.getElementById('sheetSelect').value;
  var l=document.getElementById('linkInput').value.trim();
  document.getElementById('btnDetect').disabled=!(s&&l.includes('docs.google.com/forms')&&l.includes('viewform'));
}
function goStep(n){
  currentStep=n;
  for(var i=1;i<=3;i++){
    document.getElementById('screen'+i).className='screen'+(i===n?' active':'');
    document.getElementById('sn'+i).className='step-num'+(i<n?' done':i===n?' active':'');
    document.getElementById('sl'+i).className='step-lbl'+(i===n?' active':'');
  }
  document.getElementById('con1').className='connector'+(n>1?' done':'');
  document.getElementById('con2').className='connector'+(n>2?' done':'');
}
function goDetect(){
  goStep(2);
  document.getElementById('detectingState').style.display='block';
  document.getElementById('detectResult').style.display='none';
  document.getElementById('detectError').style.display='none';
  var steps=['Connecting to server...','Fetching form metadata...','Parsing field types...','Mapping columns to entry IDs...','Validating data...'];
  var i=0;
  var iv=setInterval(function(){if(i<steps.length)document.getElementById('detectMsg').textContent=steps[i++];else clearInterval(iv);},400);
  var sheet=document.getElementById('sheetSelect').value;
  var link=document.getElementById('linkInput').value.trim();
  google.script.run
    .withSuccessHandler(function(res){
      clearInterval(iv);
      document.getElementById('detectingState').style.display='none';
      if(!res.success){document.getElementById('detectErrMsg').textContent=res.error||'Detection failed';document.getElementById('detectError').style.display='block';return;}
      detectData=res;showDetectResult(res);
    })
    .withFailureHandler(function(e){
      clearInterval(iv);
      document.getElementById('detectingState').style.display='none';
      document.getElementById('detectErrMsg').textContent=e.message||'Unknown error';
      document.getElementById('detectError').style.display='block';
    })
    .detectForm(link,sheet);
}
function showDetectResult(res){
  var fc=Object.keys(res.field_types||{}).length;
  document.getElementById('statPending').textContent=res.pendingCount||0;
  document.getElementById('statFields').textContent=fc;
  document.getElementById('statDone').textContent=res.submittedCount||0;
  document.getElementById('detectOkMsg').textContent=fc+' fields detected - '+(res.pendingCount||0)+' rows pending';
  var mapping=res.column_mapping||{},types=res.field_types||{},html='';
  Object.keys(mapping).forEach(function(col){
    var entry=mapping[col],type=types[entry]||'text',warn=!type||type==='unknown';
    html+='<div class="map-row"><span class="map-col">'+col+'</span><span class="map-arr">→</span><span class="map-entry">'+entry+'</span><span class="map-badge'+(warn?' warn':'')+'" >'+type+'</span></div>';
  });
  document.getElementById('mapCard').innerHTML=html||'<div style="font-size:11px;color:#888">No mapping found</div>';
  if(res.mapping_error){document.getElementById('warnMsg').textContent=res.mapping_error;document.getElementById('warnRow').style.display='flex';}
  document.getElementById('detectResult').style.display='block';
}
function goModules(){goStep(3);}
function selectModule(m){
  selectedModule=m;
  ['submit','generate','analyze'].forEach(function(id){
    document.getElementById('mod-'+id).className='module-card'+(id===m?' selected':'');
  });
  document.getElementById('btnLaunch').disabled=false;
}
function launchModule(){
  if(!selectedModule)return;
  alert('Launching: '+selectedModule+'\\n\\nModule UI coming in the next phase.');
}
</script>
</body></html>
"""

# ── server/__init__.py ────────────────────────────────────────────────────────
files['server/__init__.py'] = ''

# ── server/main.py ────────────────────────────────────────────────────────────
files['server/main.py'] = """import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from server.routes.health   import router as health_router
from server.routes.detect   import router as detect_router
from server.routes.submit   import router as submit_router
from server.routes.generate import router as generate_router
from server.routes.analyze  import router as analyze_router

app = FastAPI(title="FormIntellect", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(health_router,   prefix="/api")
app.include_router(detect_router,   prefix="/api")
app.include_router(submit_router,   prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(analyze_router,  prefix="/api")

@app.get("/")
def root():
    return {"status": "ok", "app": "FormIntellect", "version": "1.0.0"}

if __name__ == "__main__":
    print("\\n" + "="*48)
    print("  FormIntellect Server")
    print("  Running at http://localhost:5000")
    print("  Press Ctrl+C to stop.")
    print("="*48 + "\\n")
    uvicorn.run("server.main:app", host="127.0.0.1", port=5000, reload=False)
"""

# ── server/routes/__init__.py ─────────────────────────────────────────────────
files['server/routes/__init__.py'] = ''

# ── server/routes/health.py ───────────────────────────────────────────────────
files['server/routes/health.py'] = """from fastapi import APIRouter
from datetime import datetime
router = APIRouter()

@router.get("/health")
def health():
    return {"status": "ok", "app": "FormIntellect", "version": "1.0.0", "time": datetime.now().isoformat()}
"""

# ── server/routes/detect.py ───────────────────────────────────────────────────
files['server/routes/detect.py'] = """from fastapi import APIRouter
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
"""

# ── server/routes/submit.py ───────────────────────────────────────────────────
files['server/routes/submit.py'] = """from fastapi import APIRouter
router = APIRouter()

@router.post("/submit/start")
def submit_start():
    return {"status": "stub - coming in Phase 2"}

@router.post("/submit/pause")
def submit_pause():
    return {"status": "stub"}

@router.post("/submit/resume")
def submit_resume():
    return {"status": "stub"}

@router.post("/submit/stop")
def submit_stop():
    return {"status": "stub"}

@router.get("/submit/status")
def submit_status():
    return {"status": "stub"}
"""

# ── server/routes/generate.py ─────────────────────────────────────────────────
files['server/routes/generate.py'] = """from fastapi import APIRouter
router = APIRouter()

@router.post("/generate/preview")
def generate_preview():
    return {"status": "stub - coming in Phase 3"}

@router.post("/generate/start")
def generate_start():
    return {"status": "stub"}
"""

# ── server/routes/analyze.py ──────────────────────────────────────────────────
files['server/routes/analyze.py'] = """from fastapi import APIRouter
router = APIRouter()

@router.post("/analyze")
def analyze():
    return {"status": "stub - coming in Phase 4"}
"""

# ── engine/__init__.py ────────────────────────────────────────────────────────
files['engine/__init__.py'] = ''

# ── engine/metadata.py ────────────────────────────────────────────────────────
files['engine/metadata.py'] = """import json, re, urllib.parse, requests

def extract_entry_ids(prefilled_link):
    parsed = urllib.parse.urlparse(prefilled_link)
    pairs  = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    seen, ids = set(), []
    for key, _ in pairs:
        if key.startswith("entry.") and key not in seen:
            ids.append(key); seen.add(key)
    return ids

def fetch_form_metadata(prefilled_link):
    result = {"field_types": {}, "options_by_entry": {}, "grid_info": {}, "questions_order": [], "form_title": "", "error": None}
    try:
        resp = requests.get(prefilled_link, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        result["error"] = f"Could not fetch form: {exc}"; return result
    html = resp.text
    m = re.search(r"<title>([^<]+)</title>", html)
    if m: result["form_title"] = m.group(1).replace(" - Google Forms","").strip()
    field_types = {}
    for m in re.finditer(r'name="(entry\\.\\d+)"[^>]*type="([^"]+)"', html):
        eid, itype = m.group(1), m.group(2).lower()
        if eid not in field_types: field_types[eid] = itype
        elif "checkbox" in (field_types[eid], itype): field_types[eid] = "checkbox"
    for m in re.finditer(r'<textarea[^>]*name="(entry\\.\\d+)"', html): field_types.setdefault(m.group(1), "textarea")
    for m in re.finditer(r'<select[^>]*name="(entry\\.\\d+)"', html):   field_types.setdefault(m.group(1), "select")
    blob = _parse_fb_blob(html)
    options_by_entry, grid_info, questions_order = {}, {}, []
    if blob:
        options_by_entry = _options_from_blob(blob)
        grid_info        = _grid_from_blob(blob)
        for eid in grid_info: field_types[eid] = "grid"
        try:
            for item in blob[1][1]:
                if not isinstance(item, list) or len(item) < 5: continue
                label = item[1] if isinstance(item[1], str) else ""
                question = item[4]
                if not isinstance(question, list): continue
                for q_item in question:
                    if not isinstance(q_item, list) or not q_item: continue
                    eid_raw = q_item[0]
                    if eid_raw is None: continue
                    eid = f"entry.{eid_raw}"
                    questions_order.append((eid, label, field_types.get(eid, "text")))
        except Exception: pass
    if not questions_order:
        for eid in extract_entry_ids(prefilled_link):
            questions_order.append((eid, eid, field_types.get(eid, "text")))
    result["field_types"] = field_types; result["options_by_entry"] = options_by_entry
    result["grid_info"] = grid_info;     result["questions_order"] = questions_order
    return result

def build_column_mapping(columns, prefilled_link, status_col):
    entry_cols    = [c for c in columns if c.startswith("entry.")]
    prefilled_ids = extract_entry_ids(prefilled_link)
    non_status    = [c for c in columns if c != status_col]
    if entry_cols: return {c: c for c in entry_cols}
    if prefilled_ids:
        matched = [c for c in prefilled_ids if c in columns]
        if matched: return {c: c for c in matched}
        if len(prefilled_ids) == len(non_status): return dict(zip(non_status, prefilled_ids))
    raise ValueError("Cannot map columns to entry IDs. Rename columns to entry.<id>, or ensure column count matches the prefilled link.")

def _parse_fb_blob(html):
    token = "FB_PUBLIC_LOAD_DATA_"
    idx = html.find(token)
    if idx == -1: return None
    start = html.find("[", idx)
    if start == -1: return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(html)):
        ch = html[i]
        if in_str:
            if escape: escape = False
            elif ch == "\\\\": escape = True
            elif ch == '"': in_str = False
            continue
        if ch == '"': in_str = True
        elif ch == "[": depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try: return json.loads(html[start:i+1])
                except: return None
    return None

def _options_from_blob(blob):
    result = {}
    try: items = blob[1][1]
    except: return result
    for item in items:
        if not isinstance(item, list) or len(item) < 5: continue
        question = item[4]
        if not isinstance(question, list) or not question: continue
        q0 = question[0]
        if not isinstance(q0, list) or len(q0) < 2: continue
        eid = q0[0]
        if eid is None: continue
        opts = [opt[0] for opt in q0[1] if isinstance(opt, list) and opt and isinstance(opt[0], str)] if isinstance(q0[1], list) else []
        if opts: result[f"entry.{eid}"] = opts
    return result

def _grid_from_blob(blob):
    result = {}
    try: items = blob[1][1]
    except: return result
    for item in items:
        if not isinstance(item, list) or len(item) < 5: continue
        q_label = item[1] if isinstance(item[1], str) else ""
        question = item[4]
        if not isinstance(question, list) or len(question) < 2: continue
        sub_entries, col_options, row_labels = [], [], []
        for q_item in question:
            if not isinstance(q_item, list) or len(q_item) < 2: continue
            eid = q_item[0]
            if eid is None: continue
            opts = [opt[0] for opt in q_item[1] if isinstance(opt, list) and opt and isinstance(opt[0], str)] if isinstance(q_item[1], list) else []
            if opts:
                sub_entries.append(f"entry.{eid}")
                if not col_options: col_options = opts
            row_labels.append(q_item[3] if len(q_item) > 3 and isinstance(q_item[3], str) else f"entry.{eid}")
        if len(sub_entries) >= 2:
            if len(row_labels) != len(sub_entries): row_labels = list(sub_entries)
            for i, eid in enumerate(sub_entries):
                result[eid] = {"question_label": q_label, "sub_label": row_labels[i], "all_sub_entries": sub_entries, "options": col_options}
    return result
"""

# ── engine/validator.py ───────────────────────────────────────────────────────
files['engine/validator.py'] = """import pandas as pd
from datetime import datetime

def normalize_value(raw, entry_type="text"):
    if pd.isna(raw): return "NA"
    if isinstance(raw, (pd.Timestamp, datetime)):
        if entry_type == "date":           return raw.strftime("%Y-%m-%d")
        if entry_type == "time":           return raw.strftime("%H:%M")
        if entry_type == "datetime-local": return raw.strftime("%Y-%m-%dT%H:%M")
    text = str(raw).strip()
    if not text: return "NA"
    if text.lower() in {"na","n/a","none","null"}: return text
    if entry_type == "datetime-local" and " " in text and "T" not in text:
        text = text.replace(" ","T",1)
    return text

def best_option(value, options):
    if not options: return value
    if value in options: return value
    lower_map = {o.lower(): o for o in options if isinstance(o, str)}
    matched = lower_map.get(value.lower())
    if matched: return matched
    try:
        num = float(value)
        candidates = []
        for o in options:
            try: candidates.append((abs(float(o)-num), o))
            except: pass
        if candidates: return sorted(candidates)[0][1]
    except ValueError: pass
    return options[0]

def auto_correct(df, pending_indices, required_columns, field_types, options_by_entry):
    corrections, errors = [], []
    for idx in pending_indices:
        for col, entry in required_columns.items():
            etype = field_types.get(entry, "text")
            value = normalize_value(df.at[idx, col], etype)
            new_val, reason = value, None
            opts = options_by_entry.get(entry)
            if opts:
                if etype == "checkbox" or "," in value:
                    parts = [v.strip() for v in value.split(",") if v.strip()]
                    fixed = [best_option(v, opts) for v in parts]
                    candidate = ", ".join(dict.fromkeys(fixed))
                    if candidate != value: new_val = candidate; reason = "normalized checkbox options"
                else:
                    candidate = best_option(value, opts)
                    if candidate != value: new_val = candidate; reason = "normalized to allowed option"
            if etype == "date":
                try:
                    new_val = pd.to_datetime(value).strftime("%Y-%m-%d")
                    if new_val != value: reason = "normalized date"
                except: errors.append((idx, col, entry, value, "invalid date")); continue
            elif etype == "time":
                try:
                    new_val = pd.to_datetime(value).strftime("%H:%M")
                    if new_val != value: reason = "normalized time"
                except: errors.append((idx, col, entry, value, "invalid time")); continue
            elif etype == "datetime-local":
                try:
                    new_val = pd.to_datetime(value).strftime("%Y-%m-%dT%H:%M")
                    if new_val != value: reason = "normalized datetime"
                except: errors.append((idx, col, entry, value, "invalid datetime")); continue
            if new_val != value:
                df.at[idx, col] = new_val
                corrections.append((idx, col, entry, value, new_val, reason))
    return corrections, errors

def validate_data(df, pending_indices, required_columns, field_types, options_by_entry):
    errors = []
    for idx in pending_indices:
        for col, entry in required_columns.items():
            etype = field_types.get(entry, "text")
            value = normalize_value(df.at[idx, col], etype)
            if etype in {"radio","select"} and "," in value:
                errors.append((idx, col, entry, value, "multiple values for single-choice")); continue
            opts = options_by_entry.get(entry)
            if opts:
                parts = [v.strip() for v in value.split(",") if v.strip()] if (etype=="checkbox" or "," in value) else [value]
                bad = [v for v in parts if v not in opts]
                if bad: errors.append((idx, col, entry, value, f"not in options: {', '.join(bad)}")); continue
            if etype == "date":
                try: datetime.strptime(value, "%Y-%m-%d")
                except: errors.append((idx, col, entry, value, "invalid date (YYYY-MM-DD)"))
            elif etype == "time":
                valid = any(True for fmt in ("%H:%M","%H:%M:%S") if _try_parse(value,fmt))
                if not valid: errors.append((idx, col, entry, value, "invalid time (HH:MM)"))
            elif etype == "datetime-local":
                valid = any(True for fmt in ("%Y-%m-%dT%H:%M","%Y-%m-%dT%H:%M:%S") if _try_parse(value,fmt))
                if not valid: errors.append((idx, col, entry, value, "invalid datetime (YYYY-MM-DDTHH:MM)"))
    return errors

def _try_parse(value, fmt):
    try: datetime.strptime(value, fmt); return True
    except: return False
"""

# ── engine stubs ──────────────────────────────────────────────────────────────
files['engine/scheduler.py']   = '# Phase 2 — scheduler logic coming soon\n'
files['engine/submitter.py']   = '# Phase 2 — submitter logic coming soon\n'
files['engine/distributor.py'] = '# Phase 3 — distributor logic coming soon\n'
files['engine/analyzer.py']    = '# Phase 4 — analyzer logic coming soon\n'

# ── docs ──────────────────────────────────────────────────────────────────────
files['docs/architecture.md'] = """# FormIntellect Architecture

## Layers
- appsscript/ : Google Sheets UI — sidebar, modals, menu
- server/     : FastAPI on localhost:5000 — bridge between Sheets and Python
- engine/     : Pure Python logic — no FastAPI imports, fully testable

## Request flow (Module 1)
Sidebar -> google.script.run -> Code.gs -> UrlFetchApp -> FastAPI route -> engine -> Google Forms

## Why localhost?
No hosting cost, no latency, no auth layer, user data never leaves their machine.

## State management
Submission state is held in memory on the server. Sheet Status column is the source of truth.
Pausing is safe — already-submitted rows are skipped on resume.
"""

# ── Write all files ───────────────────────────────────────────────────────────
for path, content in files.items():
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  written  {path}")

print("\nAll files written successfully.")
print("Now run:  python -m server.main")
