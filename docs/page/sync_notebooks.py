#!/usr/bin/env python
"""Sync jupytext notebooks into the Quarto documentation site.

This script is intended to be called as a Quarto pre-render step or
manually before ``quarto render``.  It performs three actions for every
row in the CSV manifest (``notebooks.csv``):

1. Run ``jupytext --sync`` on the source ``.py`` file so that a paired
   ``.ipynb`` is generated (or updated) next to the source.
2. Copy the ``.ipynb`` into the appropriate subdirectory of the Quarto
   page (e.g. ``tutorials/``, ``howto/``).
3. Replace the notebook's metadata with a Quarto-friendly YAML header
   derived from the CSV columns (title, description, etc.).

The CSV manifest has the following columns:

    section   - target subdirectory under docs/page/ (e.g. "tutorials")
    source    - filename of the .py source in docs/notebooks/
    slug      - stem used for the output .ipynb (without extension)
    title     - page title injected into the notebook YAML
    description - short description (used in listing pages)

Usage::

    python sync_notebooks.py                 # from docs/page/
    python sync_notebooks.py --manifest notebooks.csv
    python sync_notebooks.py --dry-run       # preview without writing

The script can also be called from the project root via the Quarto
pre-render hook configured in ``_quarto.yml``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# When called as a Quarto pre-render script the working directory is the
# project root (docs/page/).  All paths are resolved relative to that.
DEFAULT_MANIFEST = "notebooks.csv"
NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent / "notebooks"
PAGE_DIR = Path(__file__).resolve().parent
SYNC_STATE_FILE = PAGE_DIR / ".sync_state.json"


# ---------------------------------------------------------------------------
# Change detection helpers
# ---------------------------------------------------------------------------


def _file_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_sync_state(state_file: Path = SYNC_STATE_FILE) -> dict[str, str]:
    """Load the persisted hash state from the JSON file.

    Returns an empty dict if the file does not exist or is corrupt.
    """
    if not state_file.exists():
        return {}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read sync state (%s); will re-sync all.", exc)
    return {}


def _save_sync_state(state: dict[str, str], state_file: Path = SYNC_STATE_FILE) -> None:
    """Persist the hash state to the JSON file."""
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _quarto_metadata(title: str, description: str, **extra: str) -> dict:
    """Build a notebook metadata dict with Quarto YAML front-matter."""
    meta = {
        "kernelspec": {
            "display_name": "Python 3 (ipykernel)",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12.0",
        },
    }
    # Quarto reads YAML from the first Raw cell, but also honours
    # notebook-level metadata when present.  We inject nothing into
    # the notebook-level metadata beyond kernel info; the YAML lives
    # in cell 0 (see _inject_yaml_cell).
    return meta


def _yaml_front_matter(title: str, description: str, **extra: str) -> str:
    """Return a YAML front-matter string for a Quarto notebook."""
    lines = [
        "---",
        f'title: "{title}"',
        f'description: "{description}"',
    ]
    for key, value in extra.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _inject_yaml_cell(nb: dict, title: str, description: str, **extra: str) -> dict:
    """Replace or prepend a Raw YAML cell at the start of the notebook.

    Quarto reads YAML front-matter from the first cell if it is a Raw
    cell whose source starts with ``---``.  We insert one (or replace
    an existing one) so that each notebook gets the correct title and
    metadata without requiring manual edits.
    """
    yaml_source = _yaml_front_matter(title, description, **extra)
    yaml_cell = {
        "cell_type": "raw",
        "metadata": {"raw_mimetype": "text/markdown"},
        "source": [yaml_source],
    }

    cells = nb.get("cells", [])

    # If the first cell is already a raw YAML cell, replace it.
    if cells and cells[0].get("cell_type") == "raw":
        first_source = "".join(cells[0].get("source", []))
        if first_source.strip().startswith("---"):
            cells[0] = yaml_cell
            return nb

    # Otherwise, prepend.
    cells.insert(0, yaml_cell)
    nb["cells"] = cells
    return nb


def _sanitise_markdown_cells(nb: dict) -> dict:
    """Replace ``---`` horizontal rules at the start of markdown cells.

    Quarto's YAML parser treats a bare ``---`` at the beginning of any
    markdown cell as a YAML document separator and attempts to parse the
    following lines as YAML.  This causes ``YAMLException`` errors when
    the cell actually contains a standard Markdown horizontal rule
    followed by prose or headings.

    The fix replaces a leading ``---`` with ``***``, which renders
    identically as an ``<hr>`` in HTML/Markdown but is not mistaken for
    a YAML delimiter.
    """
    for cell in nb.get("cells", []):
        if cell.get("cell_type") != "markdown":
            continue
        source = cell.get("source", [])
        if not source:
            continue
        # source is a list of strings (one per line, usually with \n).
        # Check whether the first non-empty content is a bare "---".
        first = source[0]
        if first.rstrip("\n") == "---":
            source[0] = first.replace("---", "***", 1)
            logger.debug("Replaced leading '---' with '***' in markdown cell")
    return nb


def _strip_jupytext_metadata(nb: dict) -> dict:
    """Remove jupytext-specific keys from notebook metadata.

    Quarto does not need (and may be confused by) the ``jupytext``
    metadata block that jupytext injects.
    """
    metadata = nb.get("metadata", {})
    metadata.pop("jupytext", None)
    nb["metadata"] = metadata
    return nb


def sync_one(
    source: str,
    slug: str,
    section: str,
    title: str,
    description: str,
    *,
    dry_run: bool = False,
    notebooks_dir: Path = NOTEBOOKS_DIR,
    page_dir: Path = PAGE_DIR,
) -> Path | None:
    """Sync a single notebook from source .py to page .ipynb."""
    py_path = notebooks_dir / source
    if not py_path.exists():
        logger.warning("Source not found: %s", py_path)
        return None

    ipynb_name = py_path.with_suffix(".ipynb").name
    ipynb_path = notebooks_dir / ipynb_name

    # 1. jupytext --sync --execute (produces .ipynb with cell outputs)
    logger.info("jupytext --sync --execute %s", py_path)
    if not dry_run:
        result = subprocess.run(
            [sys.executable, "-m", "jupytext", "--sync", "--execute", str(py_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(
                "jupytext sync/execute failed for %s:\nstdout: %s\nstderr: %s",
                py_path,
                result.stdout,
                result.stderr,
            )
            return None

    # 2. Copy .ipynb into section subdirectory
    target_dir = page_dir / section
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{slug}.ipynb"

    logger.info("Copy %s -> %s", ipynb_path, target_path)
    if not dry_run:
        if not ipynb_path.exists():
            logger.error("Expected .ipynb not found after sync: %s", ipynb_path)
            return None
        shutil.copy2(ipynb_path, target_path)

    # 3. Inject Quarto YAML header and strip jupytext metadata
    logger.info("Inject YAML header: title=%r", title)
    if not dry_run:
        with open(target_path, "r", encoding="utf-8") as f:
            nb = json.load(f)

        nb = _strip_jupytext_metadata(nb)
        nb = _sanitise_markdown_cells(nb)
        nb = _inject_yaml_cell(nb, title, description)
        nb["metadata"] = _quarto_metadata(title, description)

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(nb, f, indent=1, ensure_ascii=False)

    return target_path


def sync_all(
    manifest: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    notebooks_dir: Path = NOTEBOOKS_DIR,
    page_dir: Path = PAGE_DIR,
    section_filter: str | None = None,
) -> list[Path]:
    """Sync all notebooks listed in the CSV manifest.

    Only notebooks whose source ``.py`` file has changed since the last
    successful sync are re-processed.  Change detection is based on
    SHA-256 hashes stored in ``.sync_state.json``.

    Args:
        manifest: Path to the CSV manifest.
        dry_run: If True, preview actions without writing files.
        force: If True, ignore cached hashes and re-sync everything.
        notebooks_dir: Directory containing the source ``.py`` files.
        page_dir: Root of the Quarto site project.
        section_filter: If set, only sync notebooks in this section.

    Returns:
        List of paths to synced ``.ipynb`` files.
    """
    state = _load_sync_state()
    results = []
    skipped = 0

    with open(manifest, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if section_filter and row["section"] != section_filter:
                continue

            source = row["source"]
            py_path = notebooks_dir / source

            # --- Change detection ---
            if not force and py_path.exists():
                current_hash = _file_hash(py_path)
                cached_hash = state.get(source)
                if cached_hash == current_hash:
                    # Also check that the target .ipynb exists; if it was
                    # deleted we must re-sync even if the source is unchanged.
                    target_path = page_dir / row["section"] / f"{row['slug']}.ipynb"
                    if target_path.exists():
                        logger.info("Up to date, skipping: %s", source)
                        skipped += 1
                        continue
                    else:
                        logger.info(
                            "Target missing, re-syncing despite unchanged source: %s",
                            source,
                        )
            else:
                current_hash = _file_hash(py_path) if py_path.exists() else None

            path = sync_one(
                source=source,
                slug=row["slug"],
                section=row["section"],
                title=row["title"],
                description=row["description"],
                dry_run=dry_run,
                notebooks_dir=notebooks_dir,
                page_dir=page_dir,
            )
            if path:
                results.append(path)
                # Update state with the new hash (only when not dry-running).
                if not dry_run and current_hash is not None:
                    state[source] = current_hash

    # Persist the updated state.
    if not dry_run:
        _save_sync_state(state)

    if skipped:
        logger.info("Skipped %d unchanged notebook(s).", skipped)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync jupytext notebooks into the Quarto site."
    )
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST,
        help="Path to the CSV manifest (default: %(default)s)",
    )
    parser.add_argument(
        "--section",
        default=None,
        help="Only sync notebooks in this section (e.g. 'tutorials')",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Ignore cached hashes and re-sync all notebooks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing files",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    manifest = Path(args.manifest)
    if not manifest.is_absolute():
        manifest = PAGE_DIR / manifest

    if not manifest.exists():
        logger.error("Manifest not found: %s", manifest)
        sys.exit(1)

    results = sync_all(
        manifest,
        dry_run=args.dry_run,
        force=args.force,
        section_filter=args.section,
    )
    logger.info("Synced %d notebook(s).", len(results))


if __name__ == "__main__":
    main()
