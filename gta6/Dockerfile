FROM python:3.11-slim

# ffmpeg for cutting/captions, fonts for burned subtitles, curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core fontconfig curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CLIPNOVA_DATA=/app/data
VOLUME /app/data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
