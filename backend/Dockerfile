FROM python:3.11-slim

WORKDIR /app

# Bumps invalidate Docker cache for layers below; use if Railway “Clear build cache”
# still serves an old image after backend-only commits.
ARG COACH_API_BUILD_TAG=2026-04-11b
RUN echo "coach_api_build_tag=${COACH_API_BUILD_TAG}"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]

