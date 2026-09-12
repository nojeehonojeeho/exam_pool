from __future__ import annotations

from tools.wrap_hwp_equation_scripts import _wrap_at_separators


def test_wrap_preserves_separators_and_is_idempotent() -> None:
    script = "a=1; b=2; c=3; d=4"
    wrapped, count = _wrap_at_separators(script, line_chars=7)
    assert count >= 1
    assert wrapped.replace("#", "").replace(" ", "") == script.replace(" ", "")
    again, again_count = _wrap_at_separators(wrapped, line_chars=7)
    assert again == wrapped
    assert again_count == 0


def test_short_script_is_unchanged() -> None:
    script = "x^2+1"
    assert _wrap_at_separators(script, line_chars=5) == (script, 0)


def test_existing_cases_break_is_not_rewritten() -> None:
    script = "cases { x (x >= 0) # -x (x < 0) }"
    assert _wrap_at_separators(script, line_chars=5) == (script, 0)
