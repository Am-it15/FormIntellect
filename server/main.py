import sys, os
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
    print("\n" + "="*48)
    print("  FormIntellect Server")
    print("  Running at http://localhost:5000")
    print("  Press Ctrl+C to stop.")
    print("="*48 + "\n")
    uvicorn.run("server.main:app", host="127.0.0.1", port=5000, reload=False)
