"""
Local read-only dashboard server for AutoPilot test evidence.
Binds to localhost only. Serves the dashboard HTML and a JSON API
that reads persisted test-run data from RESULTS_DIR (default: <repo>/results).
"""

import json
import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ENGINE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))
from orchestration.config import OrchestrationConfig  # noqa: E402

RESULTS_DIR = OrchestrationConfig.load().results_dir
WORKSPACE_ROOT = RESULTS_DIR  # evidence paths are shown relative to RESULTS_DIR
RUNS_DIR = RESULTS_DIR / "test_runs"
EVIDENCE_DIR = RESULTS_DIR / "evidence"
DASHBOARD_DIR = Path(__file__).resolve().parent
PORT = int(os.environ.get("DASHBOARD_PORT", "8470"))


def _safe_json_load(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _list_runs(limit: int = 50):
    if not RUNS_DIR.exists():
        return []
    files = sorted(RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    runs = []
    for rf in files[:limit]:
        doc = _safe_json_load(rf)
        if doc is None:
            continue
        summary = doc.get("summary") or doc.get("test_run_summary") or {}
        runs.append({
            "test_run_id": doc.get("test_run_id", rf.stem),
            "started_at": doc.get("started_at", ""),
            "completed_at": doc.get("completed_at", ""),
            "overall_status": doc.get("overall_status", "UNKNOWN"),
            "execution_mode": doc.get("execution_mode", "sequential"),
            "total_test_cases": summary.get("total_test_cases", 0),
            "executed_test_cases": summary.get("executed_test_cases", 0),
            "passed_test_cases": summary.get("passed_test_cases", 0),
            "failed_test_cases": summary.get("failed_test_cases", 0),
            "blocked_test_cases": summary.get("blocked_test_cases", 0),
            "skipped_test_cases": summary.get("skipped_test_cases", 0),
            "pass_rate": summary.get("pass_rate", 0),
            "total_duration_ms": summary.get("total_duration_ms", 0),
        })
    return runs


def _get_run_detail(run_id: str):
    fp = RUNS_DIR / f"{run_id}.json"
    if not fp.exists():
        return None
    return _safe_json_load(fp)


def _get_evidence_listing(run_id: str):
    ev_dir = EVIDENCE_DIR / run_id
    if not ev_dir.exists():
        return []
    files = []
    for p in sorted(ev_dir.iterdir()):
        if p.is_file():
            files.append({
                "filename": p.name,
                "size_bytes": p.stat().st_size,
                "path": str(p.relative_to(WORKSPACE_ROOT)),
            })
    return files


def _get_evidence_file(run_id: str, filename: str):
    safe_name = Path(filename).name
    fp = EVIDENCE_DIR / run_id / safe_name
    if not fp.exists() or not fp.is_file():
        return None
    if not str(fp.resolve()).startswith(str(EVIDENCE_DIR.resolve())):
        return None
    try:
        return fp.read_text(encoding="utf-8")
    except Exception:
        return None


class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self._serve_file(DASHBOARD_DIR / "index.html", "text/html")
        elif path == "/api/runs":
            limit = int(qs.get("limit", ["50"])[0])
            self._json_response(_list_runs(limit))
        elif path.startswith("/api/runs/") and path.count("/") == 3:
            run_id = path.split("/")[3]
            doc = _get_run_detail(run_id)
            if doc:
                self._json_response(doc)
            else:
                self._error(404, "Run not found")
        elif path.startswith("/api/evidence/"):
            parts = path.split("/")
            if len(parts) == 4:
                run_id = parts[3]
                self._json_response(_get_evidence_listing(run_id))
            elif len(parts) == 5:
                run_id = parts[3]
                filename = parts[4]
                content = _get_evidence_file(run_id, filename)
                if content is not None:
                    self._text_response(content)
                else:
                    self._error(404, "Evidence file not found")
            else:
                self._error(400, "Invalid evidence path")
        else:
            self._error(404, "Not found")

    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _text_response(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, filepath: Path, content_type: str):
        if not filepath.exists():
            self._error(404, "File not found")
            return
        body = filepath.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, message):
        body = json.dumps({"error": message}).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stderr.write(f"[dashboard] {args[0]}\n")


def main():
    server = HTTPServer(("127.0.0.1", PORT), DashboardHandler)
    print(f"AutoPilot Dashboard running at http://localhost:{PORT}")
    print(f"Reading test runs from: {RUNS_DIR}")
    print(f"Reading evidence from:  {EVIDENCE_DIR}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
