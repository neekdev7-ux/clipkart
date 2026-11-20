# ClipNova GTA 6 — Server Deploy Guide

24/7 chalane ke liye isko ek chhote VPS par deploy karo. Agent cloud par
host nahi ho sakta — wahan se koi public URL nahi milta (dashboard tum tak
pahunch hi nahi payega), VM baar-baar replace hota hai, aur RAM bhi tight
hai. VPS par sab kuch tumhare control me rehta hai.

## Option A — VPS (recommended, ~₹450/month)

**1. VPS lo** — Hetzner CX22 (~€4.15/month), Contabo ya DigitalOcean
($5–6/month). Specs: **2 vCPU, 4 GB RAM, 40 GB disk, Ubuntu 24.04**.
Buy karte waqt apna SSH key add kar do, ya root password rakh lo.

**2. SSH karo**

```bash
ssh root@TUMHARA-SERVER-IP
```

**3. Ek command chalao** — Docker install, code download, server start,
sab automatic:

```bash
curl -fsSL https://raw.githubusercontent.com/neekdev7-ux/clipkart/main/gta6/deploy.sh | bash
```

**4. Dashboard kholo** — `http://TUMHARA-SERVER-IP:8000` →
**Start monitor** dabao. Bina kisi key ke dry-run me clips detect hona
shuru ho jayenge (kuch upload nahi hoga).

**5. YouTube uploads chalu karne ke liye** (jab ready ho):
- README.md ke OAuth steps se Google Cloud client banao.
- Redirect URI ke liye server ko ek domain + HTTPS chahiye
  (`https://TUMHARA-DOMAIN/auth/youtube/callback`) — free subdomain
  (DuckDNS) + Caddy reverse proxy sabse aasan hai.
- Ya shortcut: apne PC par `http://localhost:8000` flow se
  `data/token.json` banao aur use server ke `~/clipkart/gta6/data/`
  me upload kar do.
- `.env` me `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` daalo,
  `AUTO_UPLOAD=true` karo, phir restart:
  `docker compose -f ~/clipkart/gta6/docker-compose.yml up -d`

## Option B — Apne PC par (free, par PC on rakhna hoga)

Trading bot ki tarah apne PC par bhi chala sakte ho:

```bash
git clone https://github.com/neekdev7-ux/clipkart.git
cd clipkart/gta6
cp .env.example .env
docker compose up -d --build
```

Docker Desktop install hona chahiye. Dashboard: `http://localhost:8000`.
PC band hote hi monitor ruk jayega — isliye 24/7 ke liye VPS behtar hai.

## Useful commands (server par)

```bash
docker logs -f clipnova-gta6            # live logs
docker compose -f ~/clipkart/gta6/docker-compose.yml restart   # restart
docker compose -f ~/clipkart/gta6/docker-compose.yml down      # stop
cd ~/clipkart && git pull && cd gta6 && docker compose up -d --build   # update
```

## Kharcha (estimate)

| Cheez | Cost |
| --- | --- |
| VPS (Hetzner CX22) | ~€4.15/month (~₹450) |
| Domain (optional, OAuth ke liye) | ~₹800/year ya DuckDNS free |
| YouTube Data API | Free (10,000 units/day quota) |
| Whisper / yt-dlp / ffmpeg | Free (server par chalte hain) |

Total: VPS ke alawa sab free hai.
