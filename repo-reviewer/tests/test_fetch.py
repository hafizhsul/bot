import pytest
from fetch import parse_repo_url, fetch_repo


def test_parse_basic():
    assert parse_repo_url("check https://github.com/owner/repo out") == ("owner", "repo", None)


def test_parse_branch():
    assert parse_repo_url("https://github.com/owner/repo/tree/main") == ("owner", "repo", "main")


def test_parse_none():
    assert parse_repo_url("not a repo link") is None


def test_fetch_truncates_large(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for i in range(80):
        (repo / f"f{i}.txt").write_text("x" * 2000)
    ctx, truncated = fetch_repo(str(repo), max_files=5, max_bytes=5000)
    assert truncated is True
    assert len(ctx) <= 5000 + 200
