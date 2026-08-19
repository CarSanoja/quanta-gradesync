import math

import pytest

from autocurricula.config.settings import Settings
from autocurricula.core.memory.embeddings import SemanticEmbedder, build_embedder
from tests.live.guard import live_only

pytestmark = [pytest.mark.live, live_only]

TEXT_EMBEDDING_005_DIMENSIONS = 768


def test_semantic_embedder_returns_documented_dimensionality(live_settings: Settings) -> None:
    embedder = build_embedder(live_settings)
    assert isinstance(embedder, SemanticEmbedder)
    vector = embedder("factoring quadratic trinomials in eighth grade algebra")
    assert len(vector) == TEXT_EMBEDDING_005_DIMENSIONS
    assert all(isinstance(value, float) for value in vector)
    assert math.sqrt(sum(value * value for value in vector)) > 0.0
