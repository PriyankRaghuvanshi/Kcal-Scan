from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from PIL import Image
import io
import random

app = FastAPI(title="Kcal Photo API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

KCAL_PER_100G = {
    "rice": 130,
    "chicken curry": 160,
    "butter chicken": 220,
    "dal": 110,
    "naan": 290,
    "salad": 20,
    "banana": 89,
    "apple": 52,
}

DEFAULT_PORTION_G = {
    "rice": 180,
    "chicken curry": 220,
    "butter chicken": 220,
    "dal": 200,
    "naan": 90,
    "salad": 120,
    "banana": 120,
    "apple": 150,
}

class FoodItem(BaseModel):
    name: str
    grams: int
    kcal: int
    confidence: float

class AnalyzeResponse(BaseModel):
    items: List[FoodItem]
    total_kcal: int
    note: Optional[str] = None

def mock_recognize_food(img: Image.Image) -> List[str]:
    w, h = img.size
    seed = (w * 31 + h * 17) % 10_000
    random.seed(seed)
    candidates = list(KCAL_PER_100G.keys())
    k = random.choice([2, 3, 3, 4])
    random.shuffle(candidates)
    return candidates[:k]

def kcal_for(name: str, grams: int) -> int:
    per100 = KCAL_PER_100G.get(name, 150)
    return int(round(per100 * grams / 100))

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(image: UploadFile = File(...)):
    raw = await image.read()
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return AnalyzeResponse(items=[], total_kcal=0, note="Could not read image")

    names = mock_recognize_food(img)

    items: List[FoodItem] = []
    total = 0
    for n in names:
        grams = DEFAULT_PORTION_G.get(n, 200)
        kcal = kcal_for(n, grams)
        conf = float(round(random.uniform(0.65, 0.92), 2))
        items.append(FoodItem(name=n, grams=grams, kcal=kcal, confidence=conf))
        total += kcal

    return AnalyzeResponse(items=items, total_kcal=total, note="Estimates only. Adjust portions for better accuracy.")
