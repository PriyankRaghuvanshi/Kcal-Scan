from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.api.tripdeal_mvp import router as tripdeal_mvp_router


app = FastAPI(
    title="CalorieClick Nutrition Insights API",
    version="0.1.0",
    description="AI nutrition integration layer for merged meal + supplement scan insights.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "nutrition-insights"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


app.include_router(api_router, prefix="/api/v1")
# Local-dev stubs for TripDeal Next.js MVP (search + save); not the full product API.
app.include_router(tripdeal_mvp_router, prefix="/v1")
