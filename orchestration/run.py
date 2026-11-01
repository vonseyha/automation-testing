#!/usr/bin/env python3
"""
Convenience entry point — works from any directory:
  python3 orchestration/run.py status
  cd orchestration && python3 run.py test --pillar api
"""
import sys
from pathlib import Path

_this_dir = Path(__file__).resolve().parent
_parent = _this_dir.parent

if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

from orchestration.cli import main

main()
