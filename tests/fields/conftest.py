"""Test-data provisioning for tests/fields/.

Calls :func:`timetoalign.testdata.ensure_data` at module load so that
``test_real_data_score.py`` (which resolves the Chopin Op.10/3 and
Beethoven Op.18/4 specimens via ``Path(__file__).parents[1] / "data"``)
finds the corpora on disk in both source checkouts and CI containers.

See CLAUDE.md §"Test Data Provisioning (MANDATORY)".
"""

from __future__ import annotations

from timetoalign.testdata import ensure_data

ensure_data("vienna_1x22", "score")
