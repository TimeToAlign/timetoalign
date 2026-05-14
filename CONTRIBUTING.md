# Contributing to Time To Align!

The full **Developers' Reference** lives on the documentation site at
`docs/page/contributing.qmd`. It covers:

- Repository layout and the seven-subpackage architecture (with the
  layered import-direction rules).
- Environment setup, `pip install -e ".[dev]"`, pre-commit registration.
- The canonical build/test/publish flow via `tox` (envs: default, `lint`,
  `build`, `clean`, `publish`).
- Coding standards (style, typing, Google-style docstrings, error
  handling, pitch spelling).
- The Quarto + quartodoc documentation pipeline, including how to add a
  new tutorial or how-to notebook (jupytext source → `notebooks.csv` →
  sidebar entry → glossary update).
- The hard rule that **jupytext and quarto versions may only ever be
  upgraded, never downgraded**.
- Conventional Commits and how `release-please` (running on every push to
  `main`) computes the next version. Breaking changes use both `!` *and*
  a `BREAKING CHANGE:` footer.
- IDE guidance (PyCharm preferred).

To preview the developers' reference locally:

```bash
cd timetoalign/docs/page
quartodoc build
quarto render
# open _site/contributing.html
```

Or read the rendered version on the public site:
<https://timetoalign.github.io/contributing.html>.
