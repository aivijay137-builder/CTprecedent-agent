# Makes src/ (brief.py, llm.py, ...) importable as top-level modules.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
