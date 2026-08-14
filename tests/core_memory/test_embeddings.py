from pathlib import Path

import pytest

from autocurricula.config.settings import Settings
from autocurricula.core.memory.embeddings import (
    HashingEmbedder,
    SemanticEmbedder,
    build_embedder,
)


def make_settings(tmp_path: Path, local: bool) -> Settings:
    return Settings(
        local_mode=local,
        gcp_project_id="" if local else "gradesync-proj",
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
    )


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder(dimensions=64)
    first = embedder("resuelve ecuaciones lineales con graficas")
    second = embedder("resuelve ecuaciones lineales con graficas")
    assert first == second
    assert len(first) == 64
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9


def test_hashing_embedder_returns_zero_vector_without_tokens() -> None:
    embedder = HashingEmbedder(dimensions=8)
    assert embedder("!!! ???") == [0.0] * 8


def test_hashing_embedder_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError):
        HashingEmbedder(dimensions=0)


def test_build_embedder_local_selects_hashing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, local=True)
    assert isinstance(build_embedder(settings), HashingEmbedder)


def test_build_embedder_gcp_selects_semantic_lazily(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, local=False)
    settings = settings.model_copy(update={"embedding_model": "text-embedding-005"})
    embedder = build_embedder(settings)
    assert isinstance(embedder, SemanticEmbedder)
    assert embedder.model == "text-embedding-005"
    assert embedder._client is None


class _FakeEmbeddingValues:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class _FakeEmbedding:
    def __init__(self, values: list[float]) -> None:
        self.embeddings = [_FakeEmbeddingValues(values)]


class _FakeModels:
    def __init__(self, counter: list[int]) -> None:
        self._counter = counter

    def embed_content(self, model: str, contents: str) -> _FakeEmbedding:
        self._counter[0] += 1
        return _FakeEmbedding([float(len(contents)), 1.0, 0.5])


class _FakeClient:
    def __init__(self) -> None:
        self.models = _FakeModels([0])


def test_semantic_embedder_caches_repeated_texts_without_new_calls() -> None:
    embedder = SemanticEmbedder(
        model="text-embedding-005", project="gradesync-proj", region="us-central1"
    )
    client = _FakeClient()
    embedder._client = client
    first = embedder("ministry competency chunk")
    second = embedder("ministry competency chunk")
    assert first == second
    assert client.models._counter[0] == 1
    embedder("another chunk")
    assert client.models._counter[0] == 2
