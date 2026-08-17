# Bot Telegram Download Media (YouTube MP3 / Facebook MP4 / TikTok / Instagram / X)

Bot Telegram yang mengunduh audio/video dari berbagai sumber (YouTube, Facebook, TikTok, Instagram, X), lalu mengirimkannya kembali.

## Cara kerja

1. User kirim link dari YouTube, Facebook, TikTok, Instagram, atau X ke bot.
2. Bot menawarkan pilihan format **MP3** (audio) atau **MP4** (video) lewat tombol inline; untuk MP4 user juga memilih resolusi **144p–1080p** (atau Auto).
3. Bot mengunduh media via `yt-dlp` + `ffmpeg`: MP3 dikonversi 192 kbps, MP4 di-remux tanpa re-encode.
4. Bot kirim file kembali ke user.

Semua kombinasi didukung: link dari sumber mana pun bisa jadi MP3 atau MP4 (yt-dlp mendeteksi situs otomatis).

Link Facebook yang didukung: `facebook.com/watch`, `facebook.com/reel`, `facebook.com/.../videos/`, dan `fb.watch/...`. Video Facebook yang butuh login/private tidak bisa diunduh tanpa cookie.

Catatan: **Threads tidak didukung** — yt-dlp belum punya extractor (site redirect ke `threads.com`). Video yang butuh login (mis. X/TikTok/Instagram tertentu) bisa gagal tanpa cookie.

## Setup

Butuh **Python 3.10+** dan **ffmpeg**.

### 1. Buat bot

Buka [@BotFather](https://t.me/BotFather) di Telegram, jalankan `/newbot`, lalu salin token yang diberikan.

### 2. Install dependensi

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Install ffmpeg

- Ubuntu/Debian: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: `winget install Gyan.FFmpeg` atau `choco install ffmpeg`

### 4. Set token & jalankan

```bash
cp .env.example .env
# isi TELEGRAM_BOT_TOKEN di .env
python bot.py
```

Kirim pesan `/start` ke bot di Telegram, lalu kirim link YouTube.

## Perintah

- `/start` — panduan penggunaan
- `/status` — uptime, jumlah download (persisten), sisa disk

## Batasan

- File maksimal **50 MB** (batas kirim Telegram). File lebih besar otomatis dikompres ulang ke kualitas lebih rendah (MP3: 128→64kbps; MP4: 480→360p) hingga muat; jika tetap besar, ditolak dengan pesan error.
- Satu link = satu video (`noplaylist` aktif, playlist tidak didukung).
