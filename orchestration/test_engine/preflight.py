"""
Local Environment Preflight Check.
Non-destructive verification of all prerequisites required to run the test engine.
Classifies each prerequisite as REQUIRED or OPTIONAL and produces actionable diagnostics.
Never prints passwords, tokens, API keys, or connection-string secrets.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from orchestration.config import OrchestrationConfig


class PreflightStatus:
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class PreflightCheck:
    __slots__ = ("name", "category", "required", "status", "detail", "remediation")

    def __init__(
        self,
        name: str,
        category: str,
        required: bool,
        status: str = PreflightStatus.SKIP,
        detail: str = "",
        remediation: str = "",
    ):
        self.name = name
        self.category = category
        self.required = required
        self.status = status
        self.detail = detail
        self.remediation = remediation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "required": self.required,
            "status": self.status,
            "detail": self.detail,
            "remediation": self.remediation,
        }


class PreflightRunner:
    """Runs all environment preflight checks and returns structured results."""

    def __init__(self, config: Optional[OrchestrationConfig] = None):
        self.config = config or OrchestrationConfig.load()

    def run_all(self) -> List[PreflightCheck]:
        checks: List[PreflightCheck] = []
        checks.append(self._check_python())
        checks.append(self._check_python_packages())
        checks.append(self._check_node())
        checks.append(self._check_backend_deps())
        checks.append(self._check_backend_env())
        checks.append(self._check_mongodb())
        checks.append(self._check_backend_health())
        checks.append(self._check_ui_engine())
        checks.append(self._check_jmeter())
        checks.append(self._check_ai_config())
        checks.append(self._check_write_access())
        checks.append(self._check_test_fixtures())
        return checks

    def _check_python(self) -> PreflightCheck:
        c = PreflightCheck("Python runtime", "Runtime", required=True)
        version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        if sys.version_info >= (3, 8):
            c.status = PreflightStatus.PASS
            c.detail = f"Python {version}"
        else:
            c.status = PreflightStatus.FAIL
            c.detail = f"Python {version} (minimum 3.8 required)"
            c.remediation = "Install Python 3.8+ from python.org or via brew install python3"
        return c

    def _check_python_packages(self) -> PreflightCheck:
        c = PreflightCheck("Python packages", "Runtime", required=True)
        missing = []
        for mod_name in ("json", "urllib.request", "pathlib", "csv", "concurrent.futures", "dataclasses", "enum"):
            try:
                __import__(mod_name)
            except ImportError:
                missing.append(mod_name)

        orchestration_modules = [
            "orchestration.config",
            "orchestration.test_engine.engine",
            "orchestration.test_engine.reporting",
        ]
        for mod_name in orchestration_modules:
            try:
                __import__(mod_name)
            except ImportError:
                missing.append(mod_name)

        if not missing:
            c.status = PreflightStatus.PASS
            c.detail = "All required Python packages available (stdlib + orchestration)"
        else:
            c.status = PreflightStatus.FAIL
            c.detail = f"Missing: {', '.join(missing)}"
            c.remediation = "Ensure orchestration/ is on PYTHONPATH and no stdlib shadows exist"
        return c

    def _check_node(self) -> PreflightCheck:
        c = PreflightCheck("Node.js runtime", "Runtime", required=True)
        node_bin = shutil.which("node")
        if not node_bin:
            c.status = PreflightStatus.FAIL
            c.detail = "node not found in PATH"
            c.remediation = "Install Node.js 18+ from nodejs.org or via nvm"
            return c
        try:
            res = subprocess.run([node_bin, "--version"], capture_output=True, text=True, timeout=10)
            ver = res.stdout.strip()
            c.status = PreflightStatus.PASS
            c.detail = f"Node.js {ver} at {node_bin}"
        except Exception as e:
            c.status = PreflightStatus.FAIL
            c.detail = f"node found but failed: {e}"
            c.remediation = "Verify Node.js installation"
        return c

    def _check_backend_deps(self) -> PreflightCheck:
        c = PreflightCheck("Backend dependencies", "Backend", required=True)
        ws = self.config.backend_workspace
        if not ws.exists():
            c.status = PreflightStatus.FAIL
            c.detail = f"Backend workspace not found: {ws}"
            c.remediation = f"Clone topautokh-api at {ws}, or set BACKEND_WORKSPACE in .env"
            return c

        pkg = ws / "package.json"
        if not pkg.exists():
            c.status = PreflightStatus.FAIL
            c.detail = "package.json missing in backend workspace"
            c.remediation = f"Ensure {ws}/package.json exists"
            return c

        nm = ws / "node_modules"
        if not nm.exists():
            c.status = PreflightStatus.FAIL
            c.detail = "node_modules not installed"
            c.remediation = f"Run: cd {ws} && yarn install (or npm install)"
            return c

        c.status = PreflightStatus.PASS
        c.detail = f"Backend at {ws.name}/ with node_modules installed"
        return c

    def _check_backend_env(self) -> PreflightCheck:
        c = PreflightCheck("Backend environment variables", "Backend", required=True)
        ws = self.config.backend_workspace

        env_candidates = [ws / ".env", ws / ".env.dev"]
        env_file = None
        for ef in env_candidates:
            if ef.exists():
                env_file = ef
                break

        if not env_file:
            if os.environ.get("MONGO_URI") and os.environ.get("JWT_SECRET"):
                c.status = PreflightStatus.PASS
                c.detail = "MONGO_URI and JWT_SECRET set via environment"
                return c
            c.status = PreflightStatus.FAIL
            c.detail = "No .env file found and required env vars not set"
            c.remediation = f"Copy {ws}/.env.example to {ws}/.env and fill in MONGO_URI and JWT_SECRET"
            return c

        required_vars = ["MONGO_URI", "JWT_SECRET"]
        found = []
        missing = []
        try:
            content = env_file.read_text(encoding="utf-8")
            for var in required_vars:
                has_it = False
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(f"{var}=") and len(stripped.split("=", 1)[1].strip()) > 0:
                        has_it = True
                        break
                if has_it or os.environ.get(var):
                    found.append(var)
                else:
                    missing.append(var)
        except Exception:
            missing = required_vars

        if missing:
            c.status = PreflightStatus.FAIL
            c.detail = f"Missing required vars: {', '.join(missing)} (found: {', '.join(found)})"
            c.remediation = f"Set {', '.join(missing)} in {env_file.name}"
        else:
            c.status = PreflightStatus.PASS
            c.detail = f"Required env vars configured in {env_file.name} (values redacted)"
        return c

    def _check_mongodb(self) -> PreflightCheck:
        c = PreflightCheck("MongoDB connectivity", "Database", required=True)

        mongo_uri = os.environ.get("MONGO_URI", "")
        if not mongo_uri:
            ws = self.config.backend_workspace
            for env_name in [".env", ".env.dev"]:
                ef = ws / env_name
                if ef.exists():
                    try:
                        for line in ef.read_text(encoding="utf-8").splitlines():
                            if line.strip().startswith("MONGO_URI="):
                                mongo_uri = line.strip().split("=", 1)[1].strip().strip("'\"")
                                break
                    except Exception:
                        pass
                if mongo_uri:
                    break

        host = "localhost"
        port = 27017
        if mongo_uri:
            try:
                parsed = urllib.parse.urlparse(mongo_uri)
                host = parsed.hostname or "localhost"
                port = parsed.port or 27017
            except Exception:
                pass

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        try:
            s.connect((host, port))
            s.close()
            c.status = PreflightStatus.PASS
            c.detail = f"MongoDB reachable at {host}:{port}"
        except Exception as e:
            c.status = PreflightStatus.FAIL
            c.detail = f"Cannot connect to MongoDB at {host}:{port}: {e}"
            c.remediation = "Start MongoDB: brew services start mongodb-community (or docker)"
        finally:
            s.close()
        return c

    def _check_backend_health(self) -> PreflightCheck:
        c = PreflightCheck("Backend health endpoint", "Backend", required=False)
        parsed = urllib.parse.urlparse(self.config.api_base_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 3000

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        try:
            s.connect((host, port))
            s.close()
            c.status = PreflightStatus.PASS
            c.detail = f"Backend listening on {host}:{port}"
        except Exception:
            c.status = PreflightStatus.WARN
            c.detail = f"Backend not running on {host}:{port} (API/security/performance tests will be BLOCKED)"
            c.remediation = f"Start the backend in its own terminal: cd {self.config.backend_workspace} && npm run dev (or set API_BASE_URL)"
        finally:
            s.close()
        return c

    def _check_ui_engine(self) -> PreflightCheck:
        c = PreflightCheck("UI automation engine", "UI Testing", required=False)

        playwright_bin = shutil.which("npx")
        has_playwright = False
        if playwright_bin:
            try:
                res = subprocess.run(
                    ["npx", "playwright", "--version"],
                    capture_output=True, text=True, timeout=15,
                )
                if res.returncode == 0:
                    has_playwright = True
                    c.detail = f"Playwright {res.stdout.strip()}"
            except Exception:
                pass

        chrome_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            shutil.which("google-chrome"),
            shutil.which("chromium"),
        ]
        has_browser = any(p and Path(p).exists() for p in chrome_paths if p)

        admin_page = self.config.admin_workspace
        has_angular = (admin_page / "package.json").exists()

        if has_playwright and has_browser:
            c.status = PreflightStatus.PASS
            c.detail += f" + Chrome available"
            if has_angular:
                c.detail += f" + Angular admin page found"
        elif has_playwright:
            c.status = PreflightStatus.WARN
            c.detail += " (no Chrome browser found)"
            c.remediation = "Install Chromium: npx playwright install chromium"
        else:
            utam = shutil.which("utam")
            provar = shutil.which("provar")
            if utam:
                c.status = PreflightStatus.PASS
                c.detail = f"UTAM at {utam}"
            elif provar:
                c.status = PreflightStatus.PASS
                c.detail = f"Provar at {provar}"
            else:
                c.status = PreflightStatus.WARN
                c.detail = "No UI automation engine (Playwright/UTAM/Provar) found"
                c.remediation = "Install Playwright: npm install -D @playwright/test && npx playwright install"
        return c

    def _check_jmeter(self) -> PreflightCheck:
        c = PreflightCheck("JMeter performance engine", "Performance", required=False)

        candidates = [
            self.config.jmeter_path,
            shutil.which("jmeter"),
            os.environ.get("JMETER_PATH"),
            os.environ.get("JMETER_HOME"),
        ]

        jmeter_bin = None
        for cand in candidates:
            if cand and (shutil.which(cand) or Path(cand).exists()):
                jmeter_bin = cand
                break

        if not jmeter_bin:
            c.status = PreflightStatus.WARN
            c.detail = "JMeter not found in PATH or configured locations"
            c.remediation = "Install: brew install jmeter (or set JMETER_PATH)"
            return c

        test_plan = self.config.jmeter_test_plan
        if test_plan and Path(test_plan).exists():
            c.status = PreflightStatus.PASS
            c.detail = f"JMeter at {jmeter_bin}, test plan: {Path(test_plan).name}"
        else:
            c.status = PreflightStatus.WARN
            c.detail = f"JMeter at {jmeter_bin} but smoke_test.jmx not found"
            c.remediation = f"Restore {test_plan} (or set JMETER_TEST_PLAN)"
        return c

    def _check_ai_config(self) -> PreflightCheck:
        c = PreflightCheck("AI model availability", "AI (Optional)", required=False)
        details = []

        gemini_key = self.config.gemini_api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            details.append("Gemini API key: configured (OPTIONAL, not used in default workflow)")
        else:
            details.append("Gemini API key: not set (optional — Master Agent orchestration disabled)")

        ollama_bin = shutil.which("ollama")
        if ollama_bin:
            try:
                res = subprocess.run([ollama_bin, "list"], capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    lines = [l for l in res.stdout.strip().splitlines() if l and not l.startswith("NAME")]
                    if lines:
                        model_names = [l.split()[0] for l in lines[:5]]
                        details.append(f"Ollama: installed, models: {', '.join(model_names)}")
                    else:
                        details.append("Ollama: installed but no models downloaded")
                else:
                    details.append("Ollama: installed but not running")
            except Exception:
                details.append("Ollama: installed but not responding")
        else:
            details.append("Ollama: not installed (optional local AI judge)")

        c.detail = "; ".join(details)
        c.status = PreflightStatus.PASS
        return c

    def _check_write_access(self) -> PreflightCheck:
        c = PreflightCheck("Evidence/test-run write access", "Storage", required=True)
        dirs_to_check = [
            ("test_runs", self.config.results_dir / "test_runs"),
            ("evidence", self.config.results_dir / "evidence"),
            ("audit", self.config.audit_dir),
        ]

        failures = []
        for label, d in dirs_to_check:
            try:
                d.mkdir(parents=True, exist_ok=True)
                test_file = d / ".preflight_write_test"
                test_file.write_text("ok", encoding="utf-8")
                test_file.unlink()
            except Exception as e:
                failures.append(f"{label}: {e}")

        if failures:
            c.status = PreflightStatus.FAIL
            c.detail = f"Write failures: {'; '.join(failures)}"
            c.remediation = f"Check directory permissions for {self.config.results_dir} (or set RESULTS_DIR)"
        else:
            c.status = PreflightStatus.PASS
            c.detail = "All evidence and test-run directories writable"
        return c

    def _check_test_fixtures(self) -> PreflightCheck:
        c = PreflightCheck("Test account and fixture readiness", "Fixtures", required=False)

        ws = self.config.backend_workspace
        has_jwt = bool(os.environ.get("JWT_SECRET"))
        if not has_jwt:
            for env_name in [".env", ".env.dev"]:
                ef = ws / env_name
                if ef.exists():
                    try:
                        for line in ef.read_text(encoding="utf-8").splitlines():
                            if line.strip().startswith("JWT_SECRET=") and len(line.strip().split("=", 1)[1].strip()) > 0:
                                has_jwt = True
                                break
                    except Exception:
                        pass
                if has_jwt:
                    break

        if has_jwt:
            c.status = PreflightStatus.PASS
            c.detail = "JWT_SECRET available for test token generation (value redacted)"
        else:
            c.status = PreflightStatus.WARN
            c.detail = "JWT_SECRET not found — API integration tests needing auth will use placeholder tokens"
            c.remediation = "Set JWT_SECRET in .env or environment"
        return c


def format_preflight_report(checks: List[PreflightCheck], as_json: bool = False) -> str:
    if as_json:
        return json.dumps([c.to_dict() for c in checks], indent=2)

    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("  LOCAL ENVIRONMENT PREFLIGHT CHECK")
    lines.append("=" * 80)

    required_pass = 0
    required_fail = 0
    optional_pass = 0
    optional_warn = 0

    categories: Dict[str, List[PreflightCheck]] = {}
    for c in checks:
        categories.setdefault(c.category, []).append(c)

    for cat, cat_checks in categories.items():
        lines.append(f"\n  {cat}")
        lines.append(f"  {'-' * (len(cat) + 2)}")
        for c in cat_checks:
            req_label = "REQUIRED" if c.required else "OPTIONAL"
            icon = {
                PreflightStatus.PASS: "✓",
                PreflightStatus.FAIL: "✗",
                PreflightStatus.WARN: "⚠",
                PreflightStatus.SKIP: "—",
            }.get(c.status, "?")

            lines.append(f"  {icon} [{req_label:8}] {c.name}: {c.status}")
            if c.detail:
                lines.append(f"    {c.detail}")
            if c.remediation and c.status in (PreflightStatus.FAIL, PreflightStatus.WARN):
                lines.append(f"    → {c.remediation}")

            if c.required:
                if c.status == PreflightStatus.PASS:
                    required_pass += 1
                else:
                    required_fail += 1
            else:
                if c.status == PreflightStatus.PASS:
                    optional_pass += 1
                else:
                    optional_warn += 1

    lines.append("")
    lines.append("-" * 80)
    total_req = required_pass + required_fail
    total_opt = optional_pass + optional_warn
    lines.append(f"  Required: {required_pass}/{total_req} PASS")
    lines.append(f"  Optional: {optional_pass}/{total_opt} PASS")

    if required_fail > 0:
        lines.append(f"\n  VERDICT: NOT READY — {required_fail} required prerequisite(s) failed")
        lines.append("  Fix the REQUIRED failures above before running tests.")
    else:
        lines.append(f"\n  VERDICT: READY — all required prerequisites satisfied")
        if optional_warn > 0:
            lines.append(f"  {optional_warn} optional tool(s) unavailable; affected suites will be BLOCKED.")

    lines.append("=" * 80)
    lines.append("")
    return "\n".join(lines)
