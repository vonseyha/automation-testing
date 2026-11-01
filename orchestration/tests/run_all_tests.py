"""
Master Test Runner for Orchestration Suite.
Runs all unit and integration tests.
"""

import os
import sys
import unittest
from pathlib import Path

# Unit tests must not depend on a developer's local settings file.
os.environ.setdefault("AUTOMATION_SKIP_ENV_FILE", "1")

# Add the repo root (parent of the orchestration package) to sys.path
workspace_root = Path(__file__).resolve().parent.parent.parent
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))


def run_all() -> bool:
    loader = unittest.TestLoader()
    start_dir = Path(__file__).resolve().parent
    suite = loader.discover(start_dir=str(start_dir), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
