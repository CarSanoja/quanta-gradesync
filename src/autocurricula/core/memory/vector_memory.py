import asyncio
import math
import re
from collections import Counter
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.core.memory.embeddings import HashingEmbedder, build_embedder
from autocurricula.schemas.memory import RetrievedChunk

VectorDoc = tuple[str, str, dict[str, Any]]

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_DISTANCE_FIELD = "vector_distance"
_VECTOR_FIELD = "embedding"

_hashing_embedder = HashingEmbedder()


def _tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


@runtime_checkable
class VectorMemory(Protocol):
    async def upsert(self, docs: list[VectorDoc]) -> None: ...

    async def query(self, text: str, top_k: int = 5) -> list[RetrievedChunk]: ...


class LocalVectorMemory:
    def __init__(self) -> None:
        self._docs: dict[str, VectorDoc] = {}
        self._vectors: dict[str, dict[str, float]] = {}
        self._idf: dict[str, float] = {}

    def __len__(self) -> int:
        return len(self._docs)

    async def upsert(self, docs: list[VectorDoc]) -> None:
        for doc in docs:
            self._docs[doc[0]] = doc
        self._reindex()

    async def query(self, text: str, top_k: int = 5) -> list[RetrievedChunk]:
        if top_k <= 0 or not self._docs:
            return []
        query_vector = self._tfidf(_tokenize(text))
        scored = [
            (self._cosine(query_vector, doc_vector), doc_id)
            for doc_id, doc_vector in self._vectors.items()
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        chunks: list[RetrievedChunk] = []
        for score, doc_id in scored[:top_k]:
            if score <= 0.0:
                break
            _, doc_text, metadata = self._docs[doc_id]
            source = str(metadata.get("source", doc_id))
            chunks.append(
                RetrievedChunk(text=doc_text, source=source, score=min(score, 1.0))
            )
        return chunks

    def _reindex(self) -> None:
        doc_tokens = {doc_id: _tokenize(doc[1]) for doc_id, doc in self._docs.items()}
        total_docs = len(doc_tokens)
        document_frequency: Counter[str] = Counter()
        for tokens in doc_tokens.values():
            document_frequency.update(set(tokens))
        self._idf = {
            token: math.log((total_docs + 1) / (count + 1)) + 1.0
            for token, count in document_frequency.items()
        }
        self._vectors = {
            doc_id: self._tfidf(tokens) for doc_id, tokens in doc_tokens.items()
        }

    def _tfidf(self, tokens: list[str]) -> dict[str, float]:
        counts = Counter(tokens)
        total = len(tokens)
        if total == 0:
            return {}
        return {
            token: (count / total) * self._idf.get(token, 0.0)
            for token, count in counts.items()
        }

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        if len(left) > len(right):
            left, right = right, left
        dot = sum(value * right.get(token, 0.0) for token, value in left.items())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return dot / (left_norm * right_norm)


class FirestoreVectorMemory:
    def __init__(
        self,
        client: Any,
        collection: str,
        embedder: Callable[[str], list[float]] | None = None,
    ) -> None:
        if client is None:
            raise ValueError(
                "FirestoreVectorMemory requires a Firestore client; "
                "set GRADESYNC_GCP_PROJECT_ID or keep local_mode enabled"
            )
        self._client = client
        self._collection = collection
        self._embedder = embedder or _hashing_embedder

    async def upsert(self, docs: list[VectorDoc]) -> None:
        def _write() -> None:
            collection = self._client.collection(self._collection)
            for doc_id, text, metadata in docs:
                collection.document(doc_id).set(
                    {
                        "text": text,
                        "metadata": metadata,
                        _VECTOR_FIELD: self._embedder(text),
                    }
                )

        await asyncio.to_thread(_write)

    async def query(self, text: str, top_k: int = 5) -> list[RetrievedChunk]:
        query_vector = await asyncio.to_thread(self._embedder, text)

        def _search() -> list[RetrievedChunk]:
            from google.cloud.firestore_v1.base_query import DistanceMeasure

            vector_query = self._client.collection(self._collection).find_nearest(
                vector_field=_VECTOR_FIELD,
                query_vector=query_vector,
                distance_measure=DistanceMeasure.COSINE,
                limit=top_k,
                distance_result_field=_DISTANCE_FIELD,
            )
            chunks: list[RetrievedChunk] = []
            for document in vector_query.stream():
                data = document.to_dict() or {}
                doc_text = data.get("text")
                if not isinstance(doc_text, str) or not doc_text:
                    continue
                metadata = data.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                distance = float(data.get(_DISTANCE_FIELD, 1.0))
                chunks.append(
                    RetrievedChunk(
                        text=doc_text,
                        source=str(metadata.get("source", document.id)),
                        score=min(max(1.0 - distance, 0.0), 1.0),
                    )
                )
            return chunks

        return await asyncio.to_thread(_search)


def build_vector_memory(
    settings: Settings, collection: str | None = None
) -> VectorMemory:
    if settings.local_mode:
        return LocalVectorMemory()
    return FirestoreVectorMemory(
        client=get_firestore_client(),
        collection=collection or settings.firestore_competencies_collection,
        embedder=build_embedder(settings),
    )
