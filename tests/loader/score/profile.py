"""Profiling script for Symbolic Score Loaders."""

import timeit
import io
from pathlib import Path
from timetoalign.core import TimeUnit
from timetoalign.loader.score.partitura import PartituraLoader
from timetoalign.loader.score.music21 import Music21Loader
from timetoalign.loader.score.tsv import TSVLoader

# Data Paths
DATA_DIR = Path(__file__).parents[2] / "data" / "midi" / "score"
MS3_DIR = DATA_DIR / "ms3"
CHOPIN_XML = DATA_DIR / "chopin_op10_no3.musicxml"
CHOPIN_TSV = list(MS3_DIR.glob("chopin_op10_no3.*.tsv"))

def profile_loader(loader_cls, source, name, loops=5):
    """Run timing benchmark for a loader."""
    def _run():
        loader = loader_cls(unit=TimeUnit.ticks)
        if isinstance(source, list):
            loader.load(*source)
        else:
            loader.load(source)
    
    # Warmup
    try:
        _run()
    except Exception as e:
        print(f"Skipping {name}: {e}")
        return

    # Timing
    t = timeit.timeit(_run, number=loops)
    avg_time = t / loops
    print(f"{name:<20}: {avg_time*1000:.2f} ms per run (avg of {loops})")

if __name__ == "__main__":
    print("Benchmarking Score Loaders (Chopin Op. 10 No. 3)...\n")
    
    profile_loader(PartituraLoader, CHOPIN_XML, "PartituraLoader")
    profile_loader(Music21Loader, CHOPIN_XML, "Music21Loader")
    profile_loader(TSVLoader, CHOPIN_TSV, "TSVLoader")
