import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
REFERENCE_SEED = 20260819
DEMO_SEED = 20260825


@pytest.fixture(scope="session")
def generator():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import generate_sample_batch

    return generate_sample_batch


@pytest.fixture(scope="session")
def reference_batch(generator, tmp_path_factory) -> dict[str, object]:
    target = tmp_path_factory.mktemp("bucket-reference") / "sample_batch"
    return generator.generate("reference", target, REFERENCE_SEED, 84)


@pytest.fixture(scope="session")
def demo_batch(generator, tmp_path_factory) -> dict[str, object]:
    target = tmp_path_factory.mktemp("bucket-demo") / "demo_batch"
    return generator.generate("demo", target, DEMO_SEED, 84)
