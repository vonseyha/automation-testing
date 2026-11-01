# Unit tests must not depend on a developer's local .env settings file.
import os

os.environ.setdefault("AUTOMATION_SKIP_ENV_FILE", "1")
