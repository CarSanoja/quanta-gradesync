import hashlib
import math
import re
from collections.abc import Callable
from typing import Any

from autocurricula.config.settings import Settings

Embedder = Callable[[str], list[float]]

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
EMBEDDING_DIMENSIONS = 256


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


class HashingEmbedder:
    def __init__(self, dimensions: int = EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def __call__(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in _tokenize(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class SemanticEmbedder:
    def __init__(self, model: str, *, project: str, region: str) -> None:
        if not model.strip():
            raise ValueError("model must not be blank")
        if not project.strip():
            raise ValueError("project must not be blank")
        self._model = model.strip()
        self._project = project.strip()
        self._region = region.strip() or "us-central1"
        self._client: Any | None = None
        self._cache: dict[str, list[float]] = {}

    @property
    def model(self) -> str:
        return self._model

    def __call__(self, text: str) -> list[float]:
        cached = self._cache.get(text)
        if cached is not None:
            return list(cached)
        client = self._client_or_create()
        response = client.models.embed_content(
            model=self._model, contents=text
        )
        values = [float(value) for value in response.embeddings[0].values]
        self._cache[text] = values
        return list(values)

    def _client_or_create(self) -> Any:
        if self._client is None:
            from google import genai

            self._client = genai.Client(
                vertexai=True, project=self._project, location=self._region
            )
        return self._client


def build_embedder(settings: Settings) -> Embedder:
    if settings.local_mode:
        return HashingEmbedder()
    return SemanticEmbedder(
        model=settings.embedding_model,
        project=settings.gcp_project_id,
        region=settings.gcp_region,
    )
