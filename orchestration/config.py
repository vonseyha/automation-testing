"""
Centralized Configuration for Master Agent + Specialist Reviewer Orchestration.
Per Section 14:
- PRIMARY_MODEL: gemini-3.8-flash (thinking: high)
- REVIEW_MODEL: gemini-3.1-pro-preview (thinking: high)
- REVIEW_ENABLED: true
- REVIEW_MAX_ITERATIONS: 3
- Escalation toggles: architecture, security, critical failure, persistent failure
- TEST_ENGINE_ENABLED: true
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from orchestration.core_types import ThinkingLevel


# Repository root of the automation-testing project (the folder that holds
# the `orchestration/` package, README.md and env.example).
ENGINE_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(raw: Any, base: Path) -> Path:
    """Expand ~ and resolve relative paths against `base`."""
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _load_env_file(env_file: Path) -> None:
    """Load KEY=VALUE lines into os.environ. Exported variables always win."""
    if not env_file.exists():
        return
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_key = k.strip()
                    env_val = v.strip().strip("'\"")
                    if env_val:
                        os.environ.setdefault(env_key, env_val)
    except Exception:
        pass


def load_engine_env() -> None:
    """Load `<ENGINE_ROOT>/.env`, or the file named by AUTOMATION_ENV_FILE.

    Skipped when AUTOMATION_SKIP_ENV_FILE=1 (the unit tests set this so a
    developer's local .env cannot change their results).
    """
    if os.environ.get("AUTOMATION_SKIP_ENV_FILE") == "1":
        return
    custom = os.environ.get("AUTOMATION_ENV_FILE")
    _load_env_file(_resolve_path(custom, ENGINE_ROOT) if custom else ENGINE_ROOT / ".env")


def _get_workspace_root() -> Path:
    """Folder that holds the sibling repos (topautokh-api, top-auto-1653-admin-page, ...).

    Defaults to the parent of this repository, i.e. the repos are cloned side by side.
    """
    env_root = os.environ.get("WORKSPACE_ROOT")
    if env_root:
        return _resolve_path(env_root, ENGINE_ROOT)
    return ENGINE_ROOT.parent


def _get_backend_workspace() -> Path:
    env_backend = os.environ.get("BACKEND_WORKSPACE")
    if env_backend:
        return _resolve_path(env_backend, _get_workspace_root())
    return _get_workspace_root() / "topautokh-api"


def _get_admin_workspace() -> Path:
    env_admin = os.environ.get("ADMIN_WORKSPACE")
    if env_admin:
        return _resolve_path(env_admin, _get_workspace_root())
    return _get_workspace_root() / "top-auto-1653-admin-page"


def _get_results_dir() -> Path:
    """Where test runs, evidence and audit logs are written (gitignored)."""
    env_results = os.environ.get("RESULTS_DIR")
    if env_results:
        return _resolve_path(env_results, ENGINE_ROOT)
    return ENGINE_ROOT / "results"


# BASIC test tenant used by the API / security pillars. The defaults are the
# "Top Auto Default" company and its admin employee in the team's dev database;
# on a fresh database run `node fixtures/test-identities.js --apply` and set
# TEST_BASIC_COMPANY_ID / TEST_BASIC_EMPLOYEE_ID to the ids it prints.
DEFAULT_BASIC_COMPANY_ID = "6a4082e590497f6ad8587dc8"
DEFAULT_BASIC_EMPLOYEE_ID = "6a5b4c697f7b1c31f730fb89"


def basic_company_id() -> str:
    return os.environ.get("TEST_BASIC_COMPANY_ID") or DEFAULT_BASIC_COMPANY_ID


def basic_employee_id() -> str:
    return os.environ.get("TEST_BASIC_EMPLOYEE_ID") or DEFAULT_BASIC_EMPLOYEE_ID


@dataclass
class OrchestrationConfig:
    primary_model: str = "gemini-3.8-flash"
    primary_thinking_level: ThinkingLevel = ThinkingLevel.HIGH

    review_model: str = "gemini-3.1-pro-preview"
    review_thinking_level: ThinkingLevel = ThinkingLevel.HIGH

    review_enabled: bool = True
    review_max_iterations: int = 3

    review_on_architecture_change: bool = True
    review_on_security_change: bool = True
    review_on_critical_failure: bool = True
    review_on_persistent_failure: bool = True

    test_engine_enabled: bool = True

    engine_root: Path = field(default_factory=lambda: ENGINE_ROOT)
    workspace_root: Path = field(default_factory=_get_workspace_root)
    backend_workspace: Path = field(default_factory=_get_backend_workspace)
    admin_workspace: Path = field(default_factory=_get_admin_workspace)
    results_dir: Path = field(default_factory=_get_results_dir)
    api_health_endpoint: str = "/health"
    api_base_url: str = "http://localhost:3000"

    # External Runner Integrations
    ui_test_command: Optional[str] = None
    enable_angular_headless_test: bool = False
    jmeter_path: Optional[str] = None
    jmeter_test_plan: Optional[Path] = field(
        default_factory=lambda: ENGINE_ROOT / "orchestration" / "performance" / "smoke_test.jmx"
    )
    # Security Provider Integration
    security_provider: str = "local"
    security_base_url: Optional[str] = None
    sf_target_org: Optional[str] = None
    sf_cli_path: Optional[str] = None
    security_validation_command: Optional[str] = None
    testing_center_api_url: Optional[str] = None
    agentforce_regression_batch_id: Optional[str] = None
    agentforce_api_token: Optional[str] = None
    agentforce_test_runner: Optional[str] = None

    audit_dir: Path = field(default_factory=lambda: _get_results_dir() / "audit")
    audit_jsonl_file: Path = field(
        default_factory=lambda: _get_results_dir() / "audit" / "orchestration_audit.jsonl"
    )
    audit_md_file: Path = field(
        default_factory=lambda: _get_results_dir() / "audit" / "orchestration_audit.md"
    )

    gemini_api_key: Optional[str] = None
    gemini_api_endpoint: str = "https://generativelanguage.googleapis.com/v1beta"

    # Strictness settings
    redact_secrets: bool = True
    allow_subagent_bridge: bool = True

    @classmethod
    def load(cls, config_path: Optional[str] = None, **overrides: Any) -> "OrchestrationConfig":
        """
        Loads configuration by layering:
        1. Default values
        2. config.json file
        3. .env file if present
        4. Environment variables
        5. Explicit code overrides
        """
        data: Dict[str, Any] = {}

        # 1. Load config.json if available
        json_file = Path(config_path) if config_path else Path(__file__).resolve().parent / "config.json"
        if json_file.exists():
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    for k, v in file_data.items():
                        data[k.lower()] = v
            except Exception as e:
                print(f"[WARN] Failed to read {json_file}: {e}")

        # 2. Load <ENGINE_ROOT>/.env (exported shell variables always win)
        load_engine_env()

        # 3. Environment variable mappings
        env_mappings = {
            "PRIMARY_MODEL": "primary_model",
            "PRIMARY_THINKING_LEVEL": "primary_thinking_level",
            "REVIEW_MODEL": "review_model",
            "REVIEW_THINKING_LEVEL": "review_thinking_level",
            "REVIEW_ENABLED": "review_enabled",
            "REVIEW_MAX_ITERATIONS": "review_max_iterations",
            "REVIEW_ON_ARCHITECTURE_CHANGE": "review_on_architecture_change",
            "REVIEW_ON_SECURITY_CHANGE": "review_on_security_change",
            "REVIEW_ON_CRITICAL_FAILURE": "review_on_critical_failure",
            "REVIEW_ON_PERSISTENT_FAILURE": "review_on_persistent_failure",
            "TEST_ENGINE_ENABLED": "test_engine_enabled",
            "GEMINI_API_KEY": "gemini_api_key",
            "GOOGLE_API_KEY": "gemini_api_key",
            "WORKSPACE_ROOT": "workspace_root",
            "BACKEND_WORKSPACE": "backend_workspace",
            "ADMIN_WORKSPACE": "admin_workspace",
            "RESULTS_DIR": "results_dir",
            "API_HEALTH_ENDPOINT": "api_health_endpoint",
            "API_BASE_URL": "api_base_url",
            # External Runner Integrations
            "UI_TEST_COMMAND": "ui_test_command",
            "ENABLE_ANGULAR_HEADLESS_TEST": "enable_angular_headless_test",
            "JMETER_PATH": "jmeter_path",
            "JMETER_HOME": "jmeter_path",
            "JMETER_TEST_PLAN": "jmeter_test_plan",
            "SECURITY_PROVIDER": "security_provider",
            "SECURITY_BASE_URL": "security_base_url",
            "SF_TARGET_ORG": "sf_target_org",
            "SALESFORCE_ORG_ALIAS": "sf_target_org",
            "SF_CLI_PATH": "sf_cli_path",
            "SECURITY_VALIDATION_COMMAND": "security_validation_command",
            "TESTING_CENTER_API_URL": "testing_center_api_url",
            "AGENTFORCE_TESTING_CENTER_URL": "testing_center_api_url",
            "AGENTFORCE_REGRESSION_BATCH_ID": "agentforce_regression_batch_id",
            "AGENTFORCE_API_TOKEN": "agentforce_api_token",
            "AGENTFORCE_TEST_RUNNER": "agentforce_test_runner",
        }

        for env_k, field_name in env_mappings.items():
            if env_k in os.environ:
                val = os.environ[env_k]
                if val.lower() in ("true", "1", "yes"):
                    data[field_name] = True
                elif val.lower() in ("false", "0", "no"):
                    data[field_name] = False
                elif val.isdigit():
                    data[field_name] = int(val)
                else:
                    data[field_name] = val

        # 4. Overrides
        for k, v in overrides.items():
            if v is not None:
                data[k.lower()] = v

        # Convert thinking levels to enum
        primary_thinking = data.get("primary_thinking_level", "high")
        if isinstance(primary_thinking, str):
            primary_thinking = ThinkingLevel(primary_thinking.lower())

        review_thinking = data.get("review_thinking_level", "high")
        if isinstance(review_thinking, str):
            review_thinking = ThinkingLevel(review_thinking.lower())

        ws_raw = data.get("workspace_root")
        ws_root = _resolve_path(ws_raw, ENGINE_ROOT) if ws_raw else _get_workspace_root()

        results_raw = data.get("results_dir")
        results_d = _resolve_path(results_raw, ENGINE_ROOT) if results_raw else _get_results_dir()
        audit_d = results_d / "audit"

        # Sibling repos: relative values resolve against WORKSPACE_ROOT
        backend_raw = data.get("backend_workspace")
        backend_ws = _resolve_path(backend_raw, ws_root) if backend_raw else (ws_root / "topautokh-api").resolve()
        admin_raw = data.get("admin_workspace")
        admin_ws = _resolve_path(admin_raw, ws_root) if admin_raw else (ws_root / "top-auto-1653-admin-page").resolve()

        # Engine-owned files: relative values resolve against ENGINE_ROOT
        jmeter_plan_raw = data.get("jmeter_test_plan")
        if jmeter_plan_raw:
            jmeter_plan = _resolve_path(jmeter_plan_raw, ENGINE_ROOT)
        else:
            jmeter_plan = (ENGINE_ROOT / "orchestration" / "performance" / "smoke_test.jmx").resolve()

        return cls(
            primary_model=data.get("primary_model", "gemini-3.8-flash"),
            primary_thinking_level=primary_thinking,
            review_model=data.get("review_model", "gemini-3.1-pro-preview"),
            review_thinking_level=review_thinking,
            review_enabled=data.get("review_enabled", True),
            review_max_iterations=int(data.get("review_max_iterations", 3)),
            review_on_architecture_change=data.get("review_on_architecture_change", True),
            review_on_security_change=data.get("review_on_security_change", True),
            review_on_critical_failure=data.get("review_on_critical_failure", True),
            review_on_persistent_failure=data.get("review_on_persistent_failure", True),
            test_engine_enabled=data.get("test_engine_enabled", True),
            engine_root=ENGINE_ROOT,
            workspace_root=ws_root,
            backend_workspace=backend_ws,
            admin_workspace=admin_ws,
            results_dir=results_d,
            api_health_endpoint=data.get("api_health_endpoint", "/health"),
            api_base_url=data.get("api_base_url", "http://localhost:3000"),
            ui_test_command=data.get("ui_test_command"),
            enable_angular_headless_test=bool(data.get("enable_angular_headless_test", False)),
            jmeter_path=data.get("jmeter_path"),
            jmeter_test_plan=jmeter_plan,
            security_provider=data.get("security_provider", "local"),
            security_base_url=data.get("security_base_url"),
            sf_target_org=data.get("sf_target_org"),
            sf_cli_path=data.get("sf_cli_path"),
            security_validation_command=data.get("security_validation_command"),
            testing_center_api_url=data.get("testing_center_api_url"),
            agentforce_regression_batch_id=data.get("agentforce_regression_batch_id"),
            agentforce_api_token=data.get("agentforce_api_token"),
            agentforce_test_runner=data.get("agentforce_test_runner"),
            audit_dir=Path(data["audit_dir"]) if data.get("audit_dir") else audit_d,
            audit_jsonl_file=Path(data["audit_jsonl_file"]) if data.get("audit_jsonl_file") else audit_d / "orchestration_audit.jsonl",
            audit_md_file=Path(data["audit_md_file"]) if data.get("audit_md_file") else audit_d / "orchestration_audit.md",
            gemini_api_key=data.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
            gemini_api_endpoint=data.get("gemini_api_endpoint", "https://generativelanguage.googleapis.com/v1beta"),
            redact_secrets=data.get("redact_secrets", True),
            allow_subagent_bridge=data.get("allow_subagent_bridge", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "PRIMARY_MODEL": self.primary_model,
            "PRIMARY_THINKING_LEVEL": self.primary_thinking_level.value,
            "REVIEW_MODEL": self.review_model,
            "REVIEW_THINKING_LEVEL": self.review_thinking_level.value,
            "REVIEW_ENABLED": self.review_enabled,
            "REVIEW_MAX_ITERATIONS": self.review_max_iterations,
            "REVIEW_ON_ARCHITECTURE_CHANGE": self.review_on_architecture_change,
            "REVIEW_ON_SECURITY_CHANGE": self.review_on_security_change,
            "REVIEW_ON_CRITICAL_FAILURE": self.review_on_critical_failure,
            "REVIEW_ON_PERSISTENT_FAILURE": self.review_on_persistent_failure,
            "TEST_ENGINE_ENABLED": self.test_engine_enabled,
            "ENGINE_ROOT": str(self.engine_root),
            "WORKSPACE_ROOT": str(self.workspace_root),
            "BACKEND_WORKSPACE": str(self.backend_workspace),
            "ADMIN_WORKSPACE": str(self.admin_workspace),
            "RESULTS_DIR": str(self.results_dir),
            "API_HEALTH_ENDPOINT": self.api_health_endpoint,
            "API_BASE_URL": self.api_base_url,
            "UI_TEST_COMMAND": self.ui_test_command or "NOT_CONFIGURED",
            "ENABLE_ANGULAR_HEADLESS_TEST": self.enable_angular_headless_test,
            "JMETER_PATH": self.jmeter_path or "NOT_CONFIGURED",
            "JMETER_TEST_PLAN": str(self.jmeter_test_plan) if self.jmeter_test_plan else "NOT_CONFIGURED",
            "SECURITY_PROVIDER": self.security_provider,
            "SECURITY_BASE_URL": self.security_base_url or self.api_base_url,
            "SF_TARGET_ORG": self.sf_target_org or "NOT_CONFIGURED",
            "SF_CLI_PATH": self.sf_cli_path or "NOT_CONFIGURED",
            "SECURITY_VALIDATION_COMMAND": self.security_validation_command or "NOT_CONFIGURED",
            "TESTING_CENTER_API_URL": self.testing_center_api_url or "NOT_CONFIGURED",
            "AGENTFORCE_REGRESSION_BATCH_ID": self.agentforce_regression_batch_id or "NOT_CONFIGURED",
            "AGENTFORCE_API_TOKEN_CONFIGURED": bool(self.agentforce_api_token),
        }
