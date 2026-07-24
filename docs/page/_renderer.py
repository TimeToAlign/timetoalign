"""Custom quartodoc renderer for the TimeToAlign! API reference.

Extends the stock MdRenderer with support for Google-style ``Yields:``
sections, which quartodoc 0.11 does not handle out of the box; without
this, any generator docstring aborts the build with NotImplementedError.
"""

from __future__ import annotations

from plum import dispatch
from quartodoc import MdRenderer
from quartodoc._griffe_compat import docstrings as ds
from quartodoc.renderers.md_renderer import ParamRow


class Renderer(MdRenderer):
    style = "timetoalign"

    @dispatch
    def render(self, el: ds.DocstringSectionYields):
        rows = list(map(self.render, el.value))
        header = ["Name", "Type", "Description"]
        return self._render_table(rows, header, "returns")

    @dispatch
    def render(self, el: ds.DocstringYield):  # noqa: F811 (plum multiple dispatch)
        return ParamRow(
            el.name,
            el.description,
            annotation=self.render_annotation(el.annotation),
        )
