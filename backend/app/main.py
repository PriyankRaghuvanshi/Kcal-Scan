import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router


app = FastAPI(
    title="CalorieClick Nutrition Insights API",
    version="0.1.0",
    description="AI nutrition integration layer for merged meal + supplement scan insights.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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

if os.environ.get("ENABLE_TRIPDEAL_ROUTES", "").strip().lower() in {"1", "true", "yes", "on"}:
    # Deferred import: app/api/tripdeal_mvp.py lives outside this repo;
    # only import when the flag explicitly opts in for local dev.
    from app.api.tripdeal_mvp import router as tripdeal_router
    app.include_router(tripdeal_router, prefix="/v1")
