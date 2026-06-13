"""Exact-string tests for the shared affordance-HTML helper.

``affordance_html`` and ``code`` are pure deterministic functions; every
``_repr_html_`` in the library renders through them, so this is the one
canonical place the markup shape is pinned. See ``README.md`` for the
documented expectations.
"""

from __future__ import annotations

from timetoalign.display.html import affordance_html, affordance_line, code


class TestCode:
    """The ``code()`` inline-span helper."""

    def test_plain(self) -> None:
        assert code("y") == "<code>y</code>"

    def test_escapes_value(self) -> None:
        assert code("y<z") == "<code>y&lt;z</code>"

    def test_escapes_ampersand_and_quotes(self) -> None:
        assert code("a&'b") == "<code>a&amp;&#x27;b</code>"


class TestAffordanceHtml:
    """The ``affordance_html()`` card renderer."""

    def test_full_fixture_exact_string(self) -> None:
        out = affordance_html(
            "Demo",
            [("A", "x"), ("B", code("y<z"))],
            affordances=["f()", "g(1)"],
        )
        assert out == (
            "<h4>Demo</h4>\n"
            "<table>\n"
            "<tr><td><b>A</b></td><td>x</td></tr>\n"
            "<tr><td><b>B</b></td><td><code>y&lt;z</code></td></tr>\n"
            "<tr><td><b>Try</b></td><td><code>f()</code>, <code>g(1)</code></td></tr>\n"
            "</table>"
        )

    def test_title_escaped(self) -> None:
        out = affordance_html("<X>", [], affordances=None)
        assert out == "<h4>&lt;X&gt;</h4>\n<table>\n</table>"

    def test_label_escaped_value_verbatim(self) -> None:
        out = affordance_html("T", [("a<b", "<i>v</i>")], affordances=None)
        assert out == (
            "<h4>T</h4>\n"
            "<table>\n"
            "<tr><td><b>a&lt;b</b></td><td><i>v</i></td></tr>\n"
            "</table>"
        )

    def test_no_try_row_when_affordances_none(self) -> None:
        out = affordance_html("T", [("a", "1")], affordances=None)
        assert "Try" not in out

    def test_no_try_row_when_affordances_empty(self) -> None:
        out = affordance_html("T", [("a", "1")], affordances=[])
        assert "Try" not in out

    def test_single_affordance(self) -> None:
        out = affordance_html("T", [], affordances=["one()"])
        assert out == (
            "<h4>T</h4>\n"
            "<table>\n"
            "<tr><td><b>Try</b></td><td><code>one()</code></td></tr>\n"
            "</table>"
        )


class TestAffordanceLine:
    """The ``affordance_line()`` standalone footer renderer."""

    def test_full_fixture_exact_string(self) -> None:
        out = affordance_line(["a()", "b(<x>)"])
        assert out == (
            "<div style='margin-top: 4px; color: #666; font-size: 0.85em;'>"
            "Try: <code>a()</code>, <code>b(&lt;x&gt;)</code></div>"
        )

    def test_single_snippet(self) -> None:
        out = affordance_line(["one()"])
        assert out == (
            "<div style='margin-top: 4px; color: #666; font-size: 0.85em;'>"
            "Try: <code>one()</code></div>"
        )

    def test_empty_list_returns_empty_string(self) -> None:
        assert affordance_line([]) == ""

    def test_none_returns_empty_string(self) -> None:
        assert affordance_line(None) == ""
