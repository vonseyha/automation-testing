"""
Allow running the orchestration CLI as:
  python3 -m orchestration <command>     (from workspace root)
  python3 .                              (from inside orchestration/)
"""
import sys
from pathlib import Path

_this_dir = Path(__file__).resolve().parent
_parent = _this_dir.parent

if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from orchestration.cli import main

main()
