"""Smoke test downloader. Jalankan: python test_downloader.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from downloader import extract_supported_url  # noqa: E402

CASES = [
    # (input, url yang diharapkan atau None)
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://youtube.com/shorts/abc123", "https://youtube.com/shorts/abc123"),
    ("https://music.youtube.com/watch?v=abc123", "https://music.youtube.com/watch?v=abc123"),
    ("https://youtu.be/abc123", "https://youtu.be/abc123"),
    ("https://www.facebook.com/watch?v=12345", "https://www.facebook.com/watch?v=12345"),
    ("https://m.facebook.com/reel/12345", "https://m.facebook.com/reel/12345"),
    ("https://fb.watch/abc/", "https://fb.watch/abc/"),
    ("https://www.tiktok.com/@user/video/123456", "https://www.tiktok.com/@user/video/123456"),
    ("https://vt.tiktok.com/abc/", "https://vt.tiktok.com/abc/"),
    ("https://vm.tiktok.com/abc", "https://vm.tiktok.com/abc"),
    ("https://www.instagram.com/reel/abc/", "https://www.instagram.com/reel/abc/"),
    ("https://www.instagram.com/p/abc/", "https://www.instagram.com/p/abc/"),
    ("https://twitter.com/user/status/123", "https://twitter.com/user/status/123"),
    ("https://x.com/user/status/123", "https://x.com/user/status/123"),
    # link tertanam di teks
    ("lihat ini https://youtu.be/abc123 oke", "https://youtu.be/abc123"),
    # tanda baca akhir kalimat ikut terpotong
    ("lihat ini https://youtu.be/abc123.", "https://youtu.be/abc123"),
    ("https://x.com/user/status/123,", "https://x.com/user/status/123"),
    ("(https://www.tiktok.com/@user/video/123)", "https://www.tiktok.com/@user/video/123"),
    ("https://www.instagram.com/reel/abc/?utm=x.", "https://www.instagram.com/reel/abc/?utm=x"),
    # tidak didukung
    ("https://www.threads.com/@user/post/123", None),
    ("https://example.com/video/123", None),
    ("coba download video ini", None),
    ("", None),
]

fail = 0
for text, expected in CASES:
    got = extract_supported_url(text)
    if got != expected:
        fail += 1
        print(f"FAIL: {text!r}\n  expect {expected!r}\n  got    {got!r}")

if fail:
    print(f"\n{fail}/{len(CASES)} gagal")
    sys.exit(1)
print(f"OK: {len(CASES)} kasus lolos")
