"""Helper unduhan media (YouTube/Facebook/TikTok/Instagram/X) berbasis yt-dlp, dengan fallback kualitas rendah."""

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yt_dlp
from curl_cffi import CurlOpt
from curl_cffi.requests import Session

# Resolver DNS lokal gagal resolve domain tanpa record AAAA (mis. TikTok) untuk
# libcurl (curl_cffi) yang dipakai yt-dlp saat impersonation. DoH bypass-nya.
DOH_URL = "https://cloudflare-dns.com/dns-query"

_session_init = Session.__init__


def _init_with_doh(self, *args, **kwargs):
    _session_init(self, *args, **kwargs)
    self.curl.setopt(CurlOpt.DOH_URL, DOH_URL)


Session.__init__ = _init_with_doh

from yt_dlp.networking._curlcffi import CurlCFFIRH  # noqa: E402
from yt_dlp.networking.common import _REQUEST_HANDLERS  # noqa: E402

# Matikan handler urllib: resolver lokal flaky (kadang gagal resolve host tanpa
# AAAA), sedangkan CurlCFFIRH + DoH konsisten untuk semua host.
_REQUEST_HANDLERS.pop("Urllib", None)

_SAFARI_TARGETS = [
    k for k in CurlCFFIRH._SUPPORTED_IMPERSONATE_TARGET_MAP
    if str(k).startswith("safari-") and k.os != "ios"
]
SAFARI_TARGET = max(_SAFARI_TARGETS, key=lambda t: tuple(map(int, t.version.split("."))))
# Jadikan safari default: extractor yang minta impersonate=True (mis. TikTok) memakai
# target pertama map; chrome default kena WAF block TikTok.
_map = CurlCFFIRH._SUPPORTED_IMPERSONATE_TARGET_MAP
CurlCFFIRH._SUPPORTED_IMPERSONATE_TARGET_MAP = {
    SAFARI_TARGET: _map[SAFARI_TARGET], **_map
}

# Margin aman di bawah batas kirim 50 MB Telegram.
MAX_FILE_SIZE = 45 * 1024 * 1024

# Opsional: file cookie Netscape (dari browser extension "Get cookies.txt") untuk
# konten butuh login (IG/X/FB). Jika ada, dipakai yt-dlp untuk autentikasi.
COOKIES_FILE = Path(__file__).parent / "cookies.txt"

# Tingkat kualitas saat file melebihi batas (MP3 awal 192k, MP4 awal resolusi asli).
MP3_BITRATES = ["128k", "96k", "64k"]
MP4_FALLBACK_HEIGHTS = (480, 360, 240, 144)
MP4_AUTO_HEIGHTS = (480, 360)

# Sumber yang didukung (yt-dlp mendeteksi situsnya otomatis dari URL).
_SUPPORTED_RE = re.compile(
    r"(?:https?://)?"
    r"(?:"
    r"(?:www\.|m\.|music\.)?youtube\.com/(?:watch\?v=|shorts/|live/)|"
    r"(?:www\.|m\.)?youtu\.be/|"
    r"(?:www\.|m\.|mobile\.)?facebook\.com/|"
    r"(?:www\.|m\.)?fb\.watch/|"
    r"(?:www\.|m\.|vt\.|vm\.)?tiktok\.com/|"
    r"(?:www\.|m\.)?instagram\.com/|"
    r"(?:www\.|mobile\.)?twitter\.com/|"
    r"x\.com/"
    r")\S+",
    re.IGNORECASE,
)


def extract_supported_url(text: str) -> str | None:
    """Ambil URL dari sumber yang didukung (YouTube, Facebook, TikTok, Instagram, X)."""
    match = _SUPPORTED_RE.search(text)
    if not match:
        return None
    # `\S+` ikut menangkap tanda baca akhir kalimat (titik, koma, kurung, dll).
    return re.sub(r"[.,;!?)\]}'\"\u201d\u2019]+$", "", match.group(0))


class DownloadError(Exception):
    """Gagal mengunduh atau mengonversi media."""


class TooLargeError(DownloadError):
    def __init__(self, title: str, size: int):
        self.title = title
        self.size = size
        mb = size / 1024 / 1024
        super().__init__(f"'{title}' ({mb:.0f} MB) tetap melebihi batas kirim 50 MB Telegram meski sudah dikompres.")


def _reencode(path: Path, kind: str, quality: str | int) -> Path:
    """Kompres ulang file ke kualitas lebih rendah via ffmpeg."""
    tag = str(quality).replace("k", "")
    out = path.with_name(f"{path.stem}_{tag}{path.suffix}")
    if kind == "mp3":
        cmd = ["ffmpeg", "-y", "-i", str(path), "-b:a", quality, str(out)]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", str(path),
            "-vf", f"scale=-2:{quality}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
            str(out),
        ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        out.unlink(missing_ok=True)
        detail = e.stderr.decode(errors="ignore")[-200:]
        raise DownloadError(f"Gagal mengompres ulang ke {quality}: {detail}")
    if not out.exists() or out.stat().st_size == 0:
        raise DownloadError(f"Hasil kompresi tidak valid ({quality}).")
    return out


async def download_media(
    url: str,
    kind: str,
    on_progress,
    on_stage=None,
    max_height: int | None = None,
) -> tuple[Path, str]:
    """Unduh media dari URL.

    kind: "mp3" (audio) atau "mp4" (video).
    max_height: batas resolusi maksimal untuk mp4 (mis. 720); None = otomatis (terbaik, ukuran aman).
    on_progress: callable async menerima persentase 0-100.
    on_stage: callable async opsional menerima pesan tahap (mis. kompresi ulang).
    Jika file > MAX_FILE_SIZE, dikompres ulang otomatis ke kualitas lebih rendah.
    Mengembalikan (path_file, judul). Pemanggil bertanggung jawab membersihkan direktori path_file.
    """
    if kind not in ("mp3", "mp4"):
        raise ValueError(f"kind tidak dikenal: {kind}")

    if kind == "mp3":
        fmt = "bestaudio/best"
        fallbacks = MP3_BITRATES
    elif max_height:
        # Hormati pilihan resolusi user, baru kompres ulang jika masih kebesaran.
        fmt = (
            f"best[ext=mp4][height<={max_height}]/best[height<={max_height}]/"
            "best[ext=mp4]/best"
        )
        fallbacks = [h for h in MP4_FALLBACK_HEIGHTS if h <= max_height]
    else:
        # Otomatis: preferensi ukuran <45MB agar tidak mengunduh file raksasa.
        fmt = (
            "best[ext=mp4][filesize<45M]/best[ext=mp4][filesize_approx<45M]/"
            "best[ext=mp4]/best"
        )
        fallbacks = list(MP4_AUTO_HEIGHTS)

    workdir = Path(tempfile.mkdtemp(prefix="ytdl_"))
    loop = asyncio.get_running_loop()

    def hook(d):
        if d.get("status") == "downloading" and d.get("total_bytes"):
            pct = d["downloaded_bytes"] / d["total_bytes"] * 100
            try:
                asyncio.run_coroutine_threadsafe(on_progress(pct), loop)
            except RuntimeError:
                pass  # loop sedang shutdown

    opts = {
        "format": fmt,
        "outtmpl": str(workdir / "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 3,
        "progress_hooks": [hook],
    }
    if COOKIES_FILE.exists():
        opts["cookiefile"] = str(COOKIES_FILE)
    if kind == "mp3":
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
    else:
        # Remux cepat (tanpa re-encode) agar container pasti mp4.
        # Catatan: kunci "preferedformat" (typo) memang sesuai API yt-dlp.
        opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]

    try:
        info = None
        for attempt in range(3):
            try:
                info = await loop.run_in_executor(
                    None, lambda: yt_dlp.YoutubeDL(opts).extract_info(url, download=True)
                )
                break
            except yt_dlp.utils.DownloadError as e:
                # TikTok kadang kasih "Unexpected response" (rate-limit); ulang dengan jeda.
                if "Unexpected response" not in str(e) or attempt == 2:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
        title = info.get("title") or "media"
        files = list(workdir.glob(f"*.{kind}"))
        if not files:
            raise DownloadError(
                f"Konversi ke {kind.upper()} gagal — pastikan ffmpeg terinstal."
            )
        path = files[0]
        if path.stat().st_size > MAX_FILE_SIZE and fallbacks:
            if on_stage:
                await on_stage("File besar \u2014 mengompres ulang ke kualitas lebih rendah...")
            for quality in fallbacks:
                compressed = _reencode(path, kind, quality)
                if compressed.stat().st_size <= MAX_FILE_SIZE:
                    path.unlink(missing_ok=True)
                    path = compressed
                    break
                compressed.unlink(missing_ok=True)
        if path.stat().st_size > MAX_FILE_SIZE:
            raise TooLargeError(title, path.stat().st_size)
        return path, title
    except DownloadError:
        shutil.rmtree(workdir, ignore_errors=True)
        raise
    except yt_dlp.utils.DownloadError as e:
        shutil.rmtree(workdir, ignore_errors=True)
        if kind == "mp3" and "audio codec" in str(e).lower():
            raise DownloadError(
                "Video ini tidak memiliki audio sehingga tidak bisa dikonversi ke MP3. Coba pilih MP4."
            ) from e
        raise DownloadError(f"Tidak dapat mengunduh link ini: {e}") from e
