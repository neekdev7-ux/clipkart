# ClipNova GTA 6 Edition

An always-on API server that watches YouTube **GTA 6 live streams**,
auto-detects viral moments, cuts vertical Shorts with karaoke captions
+ GTA 6 SEO, and uploads them to your YouTube channel.

**Dry-run is the default.** Out of the box the server detects and cuts
clips and queues them for your approval — it never uploads anything
until you connect your channel and turn `AUTO_UPLOAD` on.

> **Copyright notice — read this first.** Auto-reposting other
> creators' live streams risks copyright strikes and YouTube
> reused-content issues, even with a source credit. Use this tool with
> streams you own or have permission to repost. Every clip's SEO pack
> includes a source-credit line, but credit is not a substitute for
> permission.

## How it works

1. **Discover** — every 2 minutes the monitor searches YouTube for
   live GTA 6 streams (yt-dlp search, or the YouTube Data API when
   `YOUTUBE_API_KEY` is set) and adds them to the watchlist.
2. **Record** — each watched stream is recorded with ffmpeg in rolling
   5-minute segments; old segments auto-delete (retention + disk cap).
3. **Detect** — finished segments are transcribed with Whisper and
   scored 0–100 by the GTA 6 hype scorer (Vice City / Lucia / leaks /
   heists / police chases + Hindi/Hinglish hype words, hook strength,
   audio energy, and an optional live-chat spike bonus).
4. **Cut** — top moments become 1080×1920 MP4s with word-by-word
   karaoke captions and a GTA 6 SEO pack (3 titles, description with
   source credit, hashtags, tags).
5. **Upload** — in dry-run mode clips wait in the dashboard for your
   approve / reject / upload click. With `AUTO_UPLOAD=true` and a
   connected channel, uploads happen automatically, quota-guarded
   (default max 6/day — one upload costs 1600 of the 10,000 default
   daily API units).

The original ClipNova flow (paste any YouTube link, get Shorts) is
still included at the bottom of the dashboard.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # ffmpeg must be installed
cp .env.example .env              # edit if you want (works with defaults)
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — press **Start monitor** and watch the
dashboard. Clips appear in the queue as stream segments finish.

## Deploy

### VPS (recommended for always-on monitoring)

```bash
# 2 vCPU / 4GB RAM minimum, 20GB+ disk, Ubuntu 22.04+
sudo apt install ffmpeg python3-venv
sudo mkdir -p /opt/clipnova-gta6 && sudo chown $USER /opt/clipnova-gta6
# copy the app to /opt/clipnova-gta6, then:
python3 -m venv /opt/clipnova-gta6/.venv
/opt/clipnova-gta6/.venv/bin/pip install -r /opt/clipnova-gta6/requirements.txt
cp /opt/clipnova-gta6/.env.example /opt/clipnova-gta6/.env  # fill it in
sudo cp /opt/clipnova-gta6/clipnova-gta6.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clipnova-gta6
sudo journalctl -u clipnova-gta6 -f
```

Or with Docker:

```bash
docker compose up -d --build
```

### Render / Railway

- **Render:** push the repo, create from `render.yaml` (Blueprint),
  set the `sync: false` env vars in the dashboard. Use a paid plan +
  persistent disk — the free tier sleeps and has no disk.
- **Railway:** deploy from the Dockerfile, add a volume mounted at
  `/app/data`, set env vars from `.env.example`.

## Connect your YouTube channel (for uploads)

Uploads need a Google Cloud OAuth client. Exact steps:

1. Go to https://console.cloud.google.com/ and create a project
   (or pick an existing one).
2. **APIs & Services → Library** → search **YouTube Data API v3** →
   **Enable**.
3. **APIs & Services → OAuth consent screen** → choose **External** →
   fill App name + your email → **Save**. (No verification needed for
   personal use; the app stays in testing mode, which is fine for your
   own channel. Add your Google account under **Test users** if it
   asks.)
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   → Application type **Web application**.
5. Under **Authorized redirect URIs** add exactly:
   - Local: `http://localhost:8000/auth/youtube/callback`
   - Server: `https://YOUR-DOMAIN/auth/youtube/callback`
   (use the same URL your server is reached at — the app builds the
   redirect URI from the request host, so it must match).
6. Click **Create**. Copy the **Client ID** and **Client secret** into
   `.env` as `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET`
   (or download the JSON as `client_secret.json` next to the app).
7. Restart the server, open **http://your-server/auth/youtube**,
   sign in with the Google account that owns the channel, and approve
   the `youtube.upload` permission. The token is saved to
   `data/token.json` (gitignored — never share it).
8. In the dashboard the YouTube status changes to **connected**.
   Review queued clips, then set `AUTO_UPLOAD=true` in `.env` and
   restart to enable automatic uploads.

Optional: **APIs & Services → Credentials → Create Credentials → API key**
→ restrict it to YouTube Data API v3 → set as `YOUTUBE_API_KEY` for
API-based discovery and live-chat spike detection. Without it the app
uses yt-dlp search and scores without chat data.

### Quota notes

- The default YouTube Data API v3 quota is **10,000 units/day**.
- One video upload costs **1,600 units** → max 6 uploads/day by
  default (`MAX_UPLOADS_PER_DAY=6`, 9,600 units).
- Discovery via API costs ~100 units/search; yt-dlp discovery costs
  nothing. The quota meter in the dashboard shows today's usage.
- If you hit quota errors, lower `MAX_UPLOADS_PER_DAY` or request a
  quota increase in Google Cloud Console.

## API

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health + monitor state |
| GET | `/api/status` | Monitor state, disk, quota, YouTube auth |
| POST | `/api/monitor/start` | Start the monitor worker |
| POST | `/api/monitor/stop` | Stop the monitor worker |
| GET | `/api/streams` | Live watchlist |
| POST | `/api/streams/watch` | Watch a stream `{url}` or search `{query}` |
| DELETE | `/api/streams/{id}` | Remove from watchlist |
| GET | `/api/clips` | Detected clip queue (`?status=`) |
| POST | `/api/clips/{id}/approve` | Approve a clip |
| POST | `/api/clips/{id}/reject` | Reject a clip |
| POST | `/api/clips/{id}/upload` | Upload (or simulate in dry-run) |
| GET | `/api/clips/{id}/download` | Download the clip MP4 |
| GET | `/api/queue` | Pending clips + upload log + quota |
| POST | `/api/jobs` | Cut Shorts from any video (original flow) |
| GET | `/api/jobs/{id}` | Job status + clips |
| GET | `/auth/youtube` | Start YouTube OAuth |
| GET | `/auth/youtube/callback` | OAuth callback |

## Configuration

See `.env.example` for every setting. The important ones:

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUTO_UPLOAD` | `false` | Real uploads only when `true` + OAuth token exists |
| `MAX_UPLOADS_PER_DAY` | `6` | Quota guard (1600 units each) |
| `MONITOR_ON_START` | `false` | Auto-start the monitor on boot |
| `GTA6_QUERIES` | GTA 6 live, ... | Discovery search queries |
| `SEGMENT_MINUTES` | `5` | Recording segment length |
| `RETENTION_HOURS` | `2` | Raw segment retention |
| `DISK_CAP_GB` | `20` | Segment disk cap (oldest deleted first) |
| `CLIP_MIN_SCORE` | `60` | Minimum score to queue a clip |
| `MAX_WATCHED_STREAMS` | `3` | Simultaneous recordings |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

No live YouTube calls in tests — everything network is mocked.

## Project layout

```
backend/
  config.py            env settings (safe defaults)
  youtube_uploader.py  YouTube Data API uploads (dry-run default, quota guard)
  streams/
    discovery.py       find live GTA 6 streams (API or yt-dlp)
    recorder.py        ffmpeg rolling-segment recorder + retention
    chat.py            optional live-chat spike detection
  gta6/
    scorer.py          GTA 6 hype scoring (on top of base scorer)
    seo.py             GTA 6 SEO packs (titles, description, hashtags, tags)
  pipeline/            reused from ClipNova: download, transcribe,
                       score, cut, captions, seo
  app/
    main.py            FastAPI server + all endpoints + OAuth flow
    monitor.py         always-on monitor worker
    segment_processor.py  segment -> clips pipeline
    store.py           SQLite: jobs, streams, clips, uploads
frontend/              dashboard (dogechain.com cream + gold theme)
tests/                 pytest (no network)
```
