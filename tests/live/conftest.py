import os
from pathlib import Path

import pytest

from autocurricula.config.genai_env import configure_genai_env
from autocurricula.config.settings import Settings
from tests.live.exam_image import render_answer_sheet


@pytest.fixture(scope="session")
def live_settings() -> Settings:
    project = os.environ.get("GRADESYNC_GCP_PROJECT_ID", "")
    if not project:
        pytest.skip("GRADESYNC_GCP_PROJECT_ID must name a real GCP project for live tests")
    settings = Settings(local_mode=False, gcp_project_id=project)
    configure_genai_env(settings)
    return settings


@pytest.fixture(scope="session")
def answer_sheet_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("live_exam")
    return render_answer_sheet(directory / "submission-page-1.jpg")
