# ClipNova

Turn a long YouTube video into viral vertical Shorts — with auto captions
and a full SEO pack (titles, description, hashtags, tags) per clip.

Paste a YouTube link → ClipNova downloads the video, transcribes it with
Whisper, scores every 30–60s window 0–100 for virality, and cuts the best
moments into 1080×1920 MP4s with word-by-word karaoke captions.

> Use with videos you own or have rights to.

## GTA 6 mode

Paste a GTA 6 long-video link and ClipNova switches to GTA 6 mode:
windows are scored with an extra hype bonus for GTA 6 lexicon (Vice City,
Lucia, Jason, leaks, heists, ... — see `backend/pipeline/gta6.py`),
and each clip's SEO pack uses GTA 6 titles, hashtags (`#gta6`, `#gtavi`,
`#grandtheftauto6`, `#vicecity`, ...) and tags.

- `mode` field on `POST /api/jobs`: `"auto"` (default), `"gta6"`, `"generic"`.
- Auto-detect: GTA 6 when the video title matches GTA 6 / GTA VI /
  Grand Theft Auto, or the transcript has ≥3 distinct GTA 6 lexicon
  hits; otherwise generic. An explicit `"gta6"` / `"generic"` always wins.
- The resolved mode is stored on the job row (`mode` in `GET /api/jobs/{id}`).

## Thumbnails & quality

- Every clip gets a branded vertical thumbnail (`clip_{n}.jpg`, also at
  `GET /api/jobs/{id}/clips/{n}/thumbnail`): frame grab + gold "GTA 6"
  badge + the clip's first SEO title on a dark band.
- Best-quality encodes: CRF 18, medium preset, 192k audio.
- If the server restarts mid-job after the download finished, resume it
  without re-downloading: `python recover_job.py <job_id>`.

## How it works

1. **Download** — yt-dlp, best MP4 ≤1080p.
2. **Transcribe** — faster-whisper (base model, CPU), word-level timestamps,
   Hindi + English auto-detected.
3. **Score** — rule-based virality score per sentence-aligned window:
   hook strength (questions, numbers, power words in the first 5s),
   keyword overlap with the video title, audio energy (RMS vs average),
   sentence-boundary completeness, emotion/story words.
4. **Cut** — ffmpeg vertical 1080×1920 (center crop), ASS karaoke captions
   burned in the same encode.
5. **SEO** — 3 title variants, description + CTA, 8–12 hashtags, 8–12 tags.
   Rule-based by default; optionally upgraded via Gemini/OpenAI if a key
   is set (never required).

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# ffmpeg must be installed: apt install ffmpeg / brew install ffmpeg
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — the API and the web UI are served from the
same process. First run downloads the Whisper base model (~150MB) from
Hugging Face on the first transcription.

### Docker

```bash
docker compose up --build
```

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/jobs` | `{url, max_clips=5, clip_seconds=45, mode="auto"}` → `{job_id, status}` |
| `GET` | `/api/jobs/{id}` | Status, progress, video info, clips + SEO |
| `GET` | `/api/jobs/{id}/clips/{n}/download` | Clip MP4 download |
| `GET` | `/api/health` | Health check |

Rate limit: 3 jobs/hour per IP (in-memory, MVP-grade — see the comment in
`backend/app/main.py`; use a Redis-backed limiter for production).

## Deploy

**VPS (recommended for video work):** any 2 vCPU / 4GB RAM box with Docker:

```bash
git clone <repo> && cd clipnova
cp .env.example .env   # optional keys
docker compose up -d --build
# put Caddy/Nginx in front for HTTPS on port 80/443
```

**Render / Railway:** deploy from the repo as a Docker service (the
`Dockerfile` is the whole build). Set a persistent disk/volume mounted at
`/app/data` so jobs survive restarts, and give the service at least 4GB
RAM. Note: Whisper transcription is CPU-bound — a 10-minute video takes
roughly 1–3 minutes to transcribe on 2 vCPUs with the base model.

## Hardware & storage notes

- **CPU-only** — no GPU needed. 2 vCPU / 4GB RAM is the practical minimum;
  4 vCPU is noticeably faster for transcription + encoding.
- **Whisper base model** (~150MB) downloads once on first run and is cached
  in `~/.cache/huggingface`. Set `WHISPER_MODEL=tiny` for slower boxes.
- **Storage:** each job keeps the source video + clips under `data/jobs/`.
  Jobs older than 24h (rows + files) are deleted automatically on startup.
  Budget ~500MB–1GB per concurrent job for a 10–20 min source video.
- **Fonts:** burned captions use DejaVu Sans (installed in the Docker
  image). If caption burning fails on a bare-metal install, the pipeline
  falls back to cutting the clip without captions.

## Landing page demo (`landing/`)

Static site for GitHub Pages: hero, features, how-it-works, and an
interactive demo that runs the same scoring + SEO rules in the browser on
sample transcripts (labelled sample) or pasted text. The demo scores text
only — full video processing runs on the backend.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

Tests cover scoring, SEO, ASS captions, the API lifecycle (mocked
download/transcribe), GTA 6 hype scoring / SEO / mode auto-detect, and a
full pipeline smoke test on an ffmpeg-generated 90s video with stub
transcription. No Whisper model is downloaded by the tests.

## Project layout

```
backend/
  app/        FastAPI app, SQLite job store, pipeline runner
  pipeline/   download, transcribe, score, gta6, cut, captions, seo
frontend/     single-page UI (no build step)
landing/      static GitHub Pages site + client-side scoring demo
tests/        pytest suite
```
