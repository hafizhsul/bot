# tests/test_github_client.py
import github_client
import requests
from unittest import mock


def test_build_trending_query_default_week():
    q = github_client.build_trending_query(None, "week")
    assert "pushed:>" in q
    assert "language:" not in q


def test_build_trending_query_with_language():
    q = github_client.build_trending_query("python", "day")
    assert "language:python" in q
    assert "pushed:>" in q


def test_build_trending_query_invalid_period():
    try:
        github_client.build_trending_query(None, "year")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_search_query():
    q = github_client.build_search_query("game engine", "rust", 100)
    assert "game engine" in q
    assert "language:rust" in q
    assert "stars:>=100" in q


def test_build_search_query_min_stars_zero():
    q = github_client.build_search_query("game engine", None, 0)
    assert "stars:>=0" in q


def test_parse_item_missing_owner():
    item = {
        "full_name": "a/b",
        "html_url": "u",
        "description": "d",
        "stargazers_count": 1,
        "language": "Python",
        "forks_count": 0,
        "updated_at": "x",
    }
    p = github_client._parse_item(item)
    assert p["avatar"] is None


def test_parse_item():
    item = {
        "full_name": "octocat/hello",
        "html_url": "https://github.com/octocat/hello",
        "description": "A repo",
        "stargazers_count": 42,
        "language": "Python",
        "forks_count": 3,
        "updated_at": "2026-01-01T00:00:00Z",
        "owner": {"avatar_url": "http://img"},
    }
    p = github_client._parse_item(item)
    assert p["name"] == "octocat/hello"
    assert p["url"] == "https://github.com/octocat/hello"
    assert p["stars"] == 42
    assert p["language"] == "Python"
    assert p["forks"] == 3
    assert p["updated_at"] == "2026-01-01T00:00:00Z"
    assert p["avatar"] == "http://img"


def test_search_repositories_success():
    fake = mock.Mock()
    fake.status_code = 200
    fake.json.return_value = {
        "items": [
            {
                "full_name": "a/b",
                "html_url": "u",
                "description": "d",
                "stargazers_count": 1,
                "language": "Python",
                "forks_count": 0,
                "updated_at": "x",
                "owner": {"avatar_url": "y"},
            }
        ]
    }
    with mock.patch("github_client.requests.get", return_value=fake) as get:
        items = github_client.search_repositories("q")
    assert len(items) == 1
    assert items[0]["name"] == "a/b"
    assert get.call_args.kwargs["params"]["sort"] == "stars"


def test_search_repositories_passes_sort_param():
    fake = mock.Mock()
    fake.status_code = 200
    fake.json.return_value = {"items": []}
    with mock.patch("github_client.requests.get", return_value=fake) as get:
        github_client.search_repositories("q", sort="updated")
    assert get.call_args.kwargs["params"]["sort"] == "updated"


def test_search_repositories_rate_limit():
    fake = mock.Mock()
    fake.status_code = 403
    with mock.patch("github_client.requests.get", return_value=fake):
        try:
            github_client.search_repositories("q")
            assert False, "expected GitHubRateLimitError"
        except github_client.GitHubRateLimitError:
            pass


def test_search_repositories_api_error():
    fake = mock.Mock()
    fake.status_code = 500
    with mock.patch("github_client.requests.get", return_value=fake):
        try:
            github_client.search_repositories("q")
            assert False, "expected GitHubAPIError"
        except github_client.GitHubAPIError:
            pass


def test_search_repositories_network_error():
    with mock.patch(
        "github_client.requests.get",
        side_effect=requests.exceptions.RequestException("boom"),
    ):
        try:
            github_client.search_repositories("q")
            assert False, "expected GitHubAPIError"
        except github_client.GitHubAPIError as e:
            assert "network error" in str(e)
