import os
import sys
from pathlib import Path

import pytest

from autocurricula.core.armor.llm import ARMOR_INSTRUCTION
from tests.live.guard import live_only

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = [pytest.mark.live, live_only]

API_KEY_VARS = ("GRADESYNC_GEMMA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


@pytest.fixture(scope="session")
def gemma_api_key() -> str:
    for name in API_KEY_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    pytest.skip(
        "no Gemma API key; export GRADESYNC_GEMMA_API_KEY from "
        "`gcloud secrets versions access latest --secret=gradesync-gemma-api-key "
        "--project=quanta-gradesync`"
    )


def test_gemma_writes_usable_attack_payloads(gemma_api_key: str) -> None:
    from red_team.generator import GemmaAttackGenerator
    from red_team.taxonomy import CLASSES_BY_CODE

    model = os.environ.get("GRADESYNC_GEMMA_MODEL", "gemma-4-31b-it")
    generator = GemmaAttackGenerator(gemma_api_key, model=model)

    result = generator.generate(CLASSES_BY_CODE["A1"], 3, ARMOR_INSTRUCTION)

    assert result.error == "", result.error
    assert len(result.payloads) >= 1
    assert all(payload.strip() for payload in result.payloads)
    assert all(len(payload) <= 220 for payload in result.payloads)
    assert result.output_tokens > 0
    assert not any(
        payload in CLASSES_BY_CODE["A1"].seeds for payload in result.payloads
    )


def test_gemma_writes_innocent_controls(gemma_api_key: str) -> None:
    from red_team.generator import GemmaAttackGenerator
    from red_team.taxonomy import CLASSES_BY_CODE

    model = os.environ.get("GRADESYNC_GEMMA_MODEL", "gemma-4-31b-it")
    generator = GemmaAttackGenerator(gemma_api_key, model=model)

    result = generator.generate(CLASSES_BY_CODE["C0"], 2, ARMOR_INSTRUCTION)

    assert result.error == "", result.error
    assert len(result.payloads) >= 1
