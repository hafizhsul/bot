# github_client.py
from datetime import datetime, timedelta, timezone

import requests

API_URL = "https://api.github.com/search/repositories"

PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}


class GitHubRateLimitError(Exception):
    """Raised when GitHub returns HTTP 403 (rate limit exceeded)."""


class GitHubAPIError(Exception):
    """Raised when GitHub returns a non-200, non-403 status."""


def build_trending_query(language: str | None, period: str) -> str:
    if period not in PERIOD_DAYS:
        raise ValueError("period must be one of: day, week, month")
    since = (datetime.now(timezone.utc) - timedelta(days=PERIOD_DAYS[period])).strftime(
        "%Y-%m-%d"
    )
    query = f"pushed:>{since}"
    if language:
        query += f" language:{language}"
    return query


def build_search_query(
    query: str, language: str | None, min_stars: int | None
) -> str:
    q = query
    if language:
        q += f" language:{language}"
    if min_stars is not None:
        q += f" stars:>={min_stars}"
    return q


def _parse_item(item: dict) -> dict:
    return {
        "name": item["full_name"],
        "url": item["html_url"],
        "description": item.get("description") or "No description",
        "stars": item["stargazers_count"],
        "language": item.get("language") or "Unknown",
        "forks": item["forks_count"],
        "updated_at": item["updated_at"],
        "avatar": (item.get("owner", {}) or {}).get("avatar_url"),
    }


def search_repositories(query: str, per_page: int = 5) -> list[dict]:
    params = {
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": per_page,
    }
    headers = {"Accept": "application/vnd.github+json"}
    try:
        resp = requests.get(API_URL, params=params, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        raise GitHubAPIError(f"network error: {e}")
    if resp.status_code == 403:
        raise GitHubRateLimitError()
    if resp.status_code != 200:
        raise GitHubAPIError(f"GitHub API returned status {resp.status_code}")
    data = resp.json()
    return [_parse_item(i) for i in data.get("items", [])]
