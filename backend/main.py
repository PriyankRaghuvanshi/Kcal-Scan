from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from PIL import Image
import io

app = FastAPI(title="Kcal Scan API")

# ✅ CORS FIX (required for Expo / iOS / multipart uploads)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict to your app domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Health Check ----------
@app.get("/health")
def health():
    return {"status": "ok"}

# ---------- Analyze Endpoint ----------
@app.post("/analyze")
async def analyze_image(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        image = Image.open(io.BytesIO(contents)).convert("RGB")

        # 🔮 Placeholder AI logic (replace later)
        items = [
            {"name": "dal", "grams": 200, "kcal": 220, "confidence": 0.88},
            {"name": "apple", "grams": 150, "kcal": 78, "confidence": 0.91},
            {"name": "salad", "grams": 100, "kcal": 58, "confidence": 0.85},
        ]

        total_kcal = sum(i["kcal"] for i in items)

        return {
            "total_kcal": total_kcal,
            "items": items,
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
        )

