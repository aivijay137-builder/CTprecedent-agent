"""Runs the whole test suite the way GitHub CI sees it: no registry, no pack files, empty data folder. Everything that needs them must skip itself.
Run from the Faro folder:  python Prompt_EVALS/scripts/ci_view.py"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
env = dict(os.environ, DATA_DIR=tempfile.mkdtemp(), CTG_DB_PATH=str(Path(tempfile.mkdtemp()) / "none.duckdb"), PACKS_DIR=str(Path(tempfile.mkdtemp()) / "none"))
p = subprocess.run([sys.executable, "-m", "pytest", "backend", "tests", "sync", "-q"], cwd=ROOT, env=env, capture_output=True, text=True)
print(p.stdout[-1500:])
sys.exit(p.returncode)
