"""Shared HTML rendering helpers for rich Jupyter ``_repr_html_`` output.

A single dependency-free helper, :func:`affordance_html`, renders the
uniform "interactive object" card used by loaders, EventData, and Fields.
Every card surfaces the object's API *affordances* — the labelled facts a
user needs plus a final "Try" line listing the snippets a user might call
next.

The design mirrors the inline-style approach of
:meth:`timetoalign.display.ascii.Diagram._repr_html_`: no external
dependencies, plain ``<h4>`` + ``<table>`` markup.

Style contract:

* The *label* (first element of each ``(label, value)`` row) is
  HTML-escaped by the helper.
* The *value* (second element) is emitted **verbatim** — callers wrap
  values in ``<code>`` themselves via :func:`code` when needed.
"""

from __future__ import annotations

import html

__all__ = ["affordance_html", "code"]


def code(s: str) -> str:
    """Return *s* wrapped in an HTML-escaped ``<code>`` span.

    Args:
        s: The text to render as inline code.

    Returns:
        ``<code>{escaped}</code>``.
    """
    return f"<code>{html.escape(s)}</code>"


def affordance_html(
    title: str,
    rows: list[tuple[str, str]],
    *,
    affordances: list[str] | None = None,
) -> str:
    """Render an affordance card as HTML.

    Args:
        title: Card heading (escaped by this helper).
        rows: ``(label, value)`` pairs. The *label* is escaped here; the
            *value* is emitted verbatim (callers wrap in :func:`code`).
        affordances: Optional list of invocation snippets. When non-empty,
            a final row labelled ``Try`` lists each snippet as an inline
            ``<code>`` span, joined by ``", "``.

    Returns:
        A complete ``<h4>`` + ``<table>`` HTML fragment.
    """
    parts = [f"<h4>{html.escape(title)}</h4>", "<table>"]
    for label, value in rows:
        parts.append(f"<tr><td><b>{html.escape(label)}</b></td><td>{value}</td></tr>")
    if affordances:
        snippets = ", ".join(code(s) for s in affordances)
        parts.append(f"<tr><td><b>Try</b></td><td>{snippets}</td></tr>")
    parts.append("</table>")
    return "\n".join(parts)
