import io
import logging
from PIL import Image

from fastapi import FastAPI, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kcal")

app = FastAPI(title="Kcal Scan API")

# ✅ CORS (keep wide for now; lock down later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Log EVERY request so we can see what iPhone is calling
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"INCOMING {request.method} {request.url.path}")
    resp = await call_next(request)
    logger.info(f"RESPONSE {request.method} {request.url.path} -> {resp.status_code}")
    return resp

@app.get("/")
def root():
    return {"service": "kcal-scan", "version": "railway-v1"}

@app.get("/health")
def health():
    return {"status": "ok", "version": "railway-v1"}

# (Optional) Explicit OPTIONS handler for debugging
@app.options("/analyze")
def analyze_options():
    return PlainTextResponse("ok", status_code=200)

@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        _ = Image.open(io.BytesIO(contents)).convert("RGB")

        # Placeholder result
        items = [
            {"name": "dal", "grams": 200, "kcal": 220, "confidence": 0.88},
            {"name": "apple", "grams": 150, "kcal": 78, "confidence": 0.91},
            {"name": "salad", "grams": 100, "kcal": 58, "confidence": 0.85},
        ]
        total_kcal = sum(i["kcal"] for i in items)

        return {"total_kcal": total_kcal, "items": items}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

