import os

import pytest

LIVE_ENV_VAR = "GRADESYNC_LIVE_TESTS"

live_only = pytest.mark.skipif(
    os.environ.get(LIVE_ENV_VAR) != "1",
    reason=f"live contract tests run only when {LIVE_ENV_VAR}=1",
)
