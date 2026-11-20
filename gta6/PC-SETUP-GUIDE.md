# ClipNova GTA 6 — Apne PC par setup (Windows)

Trading bot ki tarah ye tool bhi tumhare apne PC par chalega. Docker ki
zaroorat nahi — seedha Python se chalega.

## Chahiye kya

- Windows 10 ya 11
- Python 3.11+ (nahi hai to setup khud download page khol dega)
- Kam se kam 25 GB khaali disk (recordings ke liye, 20 GB cap default hai)
- PC on rakhna hoga jab tak monitor chalana hai

## Setup (ek baar, 5 minute)

**1. ZIP download karo** (chat me di gayi `clipnova-gta6.zip`) aur kahi
unzip kar lo, jaise `Desktop\clipnova-gta6`. Ya git se lo:

```bash
git clone https://github.com/neekdev7-ux/clipkart.git
cd clipkart\gta6
```

**2. `setup-pc.bat` double-click karo.** Ye sab kuch khud karega:
Python check, ffmpeg install (winget se), virtual environment, saare
packages install, `.env` banana. Pehli baar 2–3 minute lag sakte hain.

Agar Python nahi hai to python.org khul jayega — install karte waqt
**"Add python.exe to PATH"** wala tick ON rakhna, phir setup dobara
chalana.

**3. `start-clipnova.bat` double-click karo.** Browser me kholo:
`http://localhost:8000` — dashboard me **Start monitor** dabao.
Bina kisi key ke dry-run me GTA 6 clips detect hona shuru ho jayenge
(kuch upload nahi hoga).

Pehli baar Whisper ka base model (~150 MB) ek baar download hoga.

## YouTube uploads chalu karna

PC par ye VPS se aasan hai — localhost redirect ke liye domain ya HTTPS
ki zaroorat nahi hoti:

1. README.md ke OAuth steps follow karo (Google Cloud project →
   YouTube Data API v3 enable → OAuth client).
2. Redirect URI me ye daalo: `http://localhost:8000/auth/youtube/callback`
3. Client ID + secret `.env` me daalo (`YOUTUBE_CLIENT_ID`,
   `YOUTUBE_CLIENT_SECRET`), server restart karo.
4. Dashboard me `/auth/youtube` kholo, apne channel se approve karo.
5. Pehle dry-run me queued clips dekh lo, phir `.env` me
   `AUTO_UPLOAD=true` karo aur restart karo. Roz max 6 uploads
   (YouTube quota guard).

## PC on rakhne ke liye

- **Sleep band karo:** Settings → System → Power → Sleep = Never
  (warna PC sote hi monitor ruk jayega).
- Laptop hai to charger laga ke rakhna, aur lid band karne par
  "Do nothing" set karna (Control Panel → Power Options).
- PC restart hone par `start-clipnova.bat` dobara chalana hoga
  (auto-start chahiye to uska shortcut Startup folder me daal do:
  `Win + R` → `shell:startup`).

## Update karna

Naya version aaye to: git walo ke liye `git pull`, ZIP walo ke liye naya
ZIP download karke purane folder me overwrite kar do (apna `.env` aur
`data/` folder mat delete karna). Phir `setup-pc.bat` dobara chalao.

## Problem aaye to

- **Port 8000 busy:** koi aur program port 8000 use kar raha hai —
  use band karo, ya `.env` me port badlo (server start command me
  `--port 8001` karke).
- **pip install fail:** internet check karo, phir `setup-pc.bat`
  dobara chalao.
- **winget nahi mila:** Microsoft Store se "App Installer" update
  karo, ya ffmpeg https://www.gyan.dev/ffmpeg/builds/ se manually
  install karke PATH me add karo.
