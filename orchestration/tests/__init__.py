# Unit tests must not depend on a developer's local .env settings file.
import atexit
import os
import shutil
import tempfile

os.environ.setdefault("AUTOMATION_SKIP_ENV_FILE", "1")

# Unit tests must never reach a live backend, even when one is running on
# localhost:3000: some tests drive the real runners (API cases write data).
# Port 9 (discard) is closed, so every request fails fast with "connection refused".
OFFLINE_BASE_URL = "http://127.0.0.1:9"
os.environ["API_BASE_URL"] = OFFLINE_BASE_URL
os.environ["SECURITY_BASE_URL"] = OFFLINE_BASE_URL

# Unit tests must never write runs into the real results/ folder (the dashboard
# would show stub runs as real ones). Tests that pass results_dir still win.
if not os.environ.get("AUTOMATION_UNIT_RESULTS_DIR"):
    _results = tempfile.mkdtemp(prefix="automation-unit-results-")
    os.environ["AUTOMATION_UNIT_RESULTS_DIR"] = _results
    atexit.register(shutil.rmtree, _results, True)
os.environ["RESULTS_DIR"] = os.environ["AUTOMATION_UNIT_RESULTS_DIR"]
