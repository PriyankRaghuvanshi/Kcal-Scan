FROM python:3.11-slim

WORKDIR /app

# Copy ONLY backend requirements first (for caching)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend app code
COPY backend/ /app/

ENV PORT=8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]

