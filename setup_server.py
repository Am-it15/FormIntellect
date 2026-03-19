import os

os.makedirs('server/routes', exist_ok=True)

files = {}

files['server/__init__.py'] = ''

files['server/routes/__init__.py'] = ''

files['server/routes/health.py'] = \
"""from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/health")
def health():
    return {
        "status": "ok",
        "app": "FormIntellect",
        "version": "1.0.0",
        "time": datetime.now().isoformat()
    }
"""

files['server/routes/detect.py'] = \
"""from fastapi import APIRouter

router = APIRouter()

@router.post("/detect")
def detect():
    return {"status": "stub - coming in Phase 2"}
"""

files['server/routes/submit.py'] = \
"""from fastapi import APIRouter

router = APIRouter()

@router.post("/submit/start")
def submit_start():
    return {"status": "stub - coming in Phase 2"}
"""

files['server/routes/generate.py'] = \
"""from fastapi import APIRouter

router = APIRouter()

@router.post("/generate/preview")
def generate_preview():
    return {"status": "stub - coming in Phase 3"}
"""

files['server/routes/analyze.py'] = \
"""from fastapi import APIRouter

router = APIRouter()

@router.post("/analyze")
def analyze():
    return {"status": "stub - coming in Phase 4"}
"""

files['server/main.py'] = \
"""import sys
import os
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router,   prefix="/api")
app.include_router(detect_router,   prefix="/api")
app.include_router(submit_router,   prefix="/api")
app.include_router(generate_router, prefix="/api")
app.include_router(analyze_router,  prefix="/api")

@app.get("/")
def root():
    return {"status": "ok", "app": "FormIntellect", "version": "1.0.0"}

if __name__ == "__main__":
    print("")
    print("=" * 48)
    print("  FormIntellect Server")
    print("  Running at http://localhost:5000")
    print("  Press Ctrl+C to stop.")
    print("=" * 48)
    print("")
    uvicorn.run("server.main:app", host="127.0.0.1", port=5000, reload=False)
"""

for path, content in files.items():
    with open(path, 'w') as f:
        f.write(content)
    print(f"Written: {path}")

print("\nAll files written. Now run:  python -m server.main")
