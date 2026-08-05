# opencode-tg-bot

Bot Telegram sebagai remote control untuk OpenCode CLI. Kirim pesan di Telegram → dijalankan sebagai `opencode run` di server/mesin kamu → hasilnya dibalas ke chat.

## Cara pakai

```bash
# 1. Install dependency
npm install

# 2. Copy env dan isi
cp .env.example .env
```

Isi `.env`:
- `TELEGRAM_BOT_TOKEN` — buat bot baru lewat [@BotFather](https://t.me/BotFather), `/newbot`, copy token-nya.
- `ALLOWED_CHAT_IDS` — **wajib diisi**. Kirim pesan apapun ke bot kamu setelah dijalankan, chat_id kamu bakal muncul di log/reply "belum di-whitelist", masukin ke sini. Ini kritis karena tanpa whitelist siapapun yang tahu username bot bisa jalanin OpenCode (dan otomatis akses shell) di mesin kamu.
- `DEFAULT_PROJECT_DIR` — folder project default (harus ada AGENTS.md/repo yang mau kamu kerjain).
- `OPENCODE_BIN` — biarin `opencode` kalau sudah ada di PATH (cek dengan `which opencode`).

```bash
# 3. Jalankan
npm run dev
```

## Command yang tersedia

- Pesan biasa → dikirim sebagai prompt ke OpenCode di direktori aktif
- `/dir /path/ke/project` → ganti direktori kerja
- `/where` → lihat direktori aktif
- `/reset` → mulai sesi baru (bukan lanjutan dari prompt sebelumnya)

## Cara kerja

Bot spawn proses `opencode run -q --continue "<prompt>"` di direktori project yang aktif untuk chat itu (`child_process.spawn`, bukan `exec`, biar aman dari shell injection). Flag `--continue` dipakai setelah prompt pertama supaya OpenCode melanjutkan sesi sebelumnya di direktori yang sama, bukan mulai obrolan baru tiap kali.

## Deploy 24/7 (opsional)

Karena kamu di Arch + fish, paling gampang pakai `systemd` user service atau `pm2`:

```bash
npm install -g pm2
pm2 start "npm run start" --name opencode-tg-bot
pm2 save
```

## Catatan keamanan

Bot ini pada dasarnya kasih akses shell (lewat OpenCode) ke mesin kamu dari Telegram. Jangan skip whitelist `ALLOWED_CHAT_IDS`, dan jangan expose token bot ke publik. Kalau OpenCode kamu dikonfigurasi permission `bash` full-access, pertimbangkan batasi permission-nya (lihat `opencode agent create --permissions`) khusus untuk agent yang dipanggil bot ini.
