import os
import re
import subprocess
import tempfile

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist",
    "build", ".idea", ".vscode", "target", "vendor",
}
SKIP_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".pdf", ".zip",
    ".gz", ".tar", ".tgz", ".exe", ".dll", ".so", ".o", ".woff",
    ".woff2", ".ttf", ".mp4", ".mov", ".pyc",
}
MAX_FILE_BYTES = 200_000
URL_RE = re.compile(r"github\.com/([\w.\-]+)/([\w.\-]+)(?:/tree/([\w.\-]+))?")


def parse_repo_url(text: str):
    m = URL_RE.search(text)
    if not m:
        return None
    owner, repo, branch = m.group(1), m.group(2), m.group(3)
    repo = repo.removesuffix(".git")
    return owner, repo, branch


def _clone(url: str, token: str | None, branch: str | None) -> str:
    dest = tempfile.mkdtemp(prefix="repo-review-")
    auth_url = url
    if token:
        auth_url = url.replace("https://", f"https://{token}@", 1)
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [auth_url, dest]
    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
    return dest


def _read_context(root: str, max_files: int, max_bytes: int) -> tuple[str, bool]:
    parts: list[str] = []
    total = 0
    count = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if count >= max_files:
                truncated = True
                break
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXTS:
                continue
            path = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if size > MAX_FILE_BYTES or size == 0:
                continue
            rel = os.path.relpath(path, root)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    body = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            snippet = f"\n# === {rel} ===\n{body}\n"
            if total + len(snippet) > max_bytes:
                truncated = True
                break
            parts.append(snippet)
            total += len(snippet)
            count += 1
        if truncated:
            break
    return "".join(parts), truncated


def fetch_repo(url: str, token: str | None = None, max_files: int = 50,
               max_bytes: int = 40000) -> tuple[str, bool]:
    branch = None
    parsed = parse_repo_url(url)
    if parsed:
        branch = parsed[2]
    local = os.path.isdir(url)
    dest = url if local else _clone(url, token, branch)
    try:
        context, truncated = _read_context(dest, max_files, max_bytes)
    finally:
        if not local:
            subprocess.run(["rm", "-rf", dest], check=False)
    return context, truncated
