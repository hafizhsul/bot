from format import _trim, build_embed, error_embed


def test_trim_under_1024():
    assert _trim("x" * 50, 1024) == "x" * 50


def test_trim_over_1024():
    out = _trim("y" * 2000, 1024)
    assert len(out) <= 1024
    assert out.endswith("…")


def test_build_embed_has_fields():
    e = build_embed(
        {"score": 7, "summary": "ok", "pros": ["a"], "cons": ["b"],
         "risks": ["c"], "suggestions": ["d"]},
        "https://github.com/o/r", False,
    )
    assert e.title
    for f in e.fields:
        assert len(f.value) <= 1024


def test_error_embed():
    e = error_embed("boom")
    assert "boom" in e.description
