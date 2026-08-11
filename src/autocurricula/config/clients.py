from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from autocurricula.config.settings import get_settings

if TYPE_CHECKING:
    from google.cloud.firestore import Client as FirestoreClient
    from google.cloud.pubsub_v1 import PublisherClient
    from google.cloud.storage import Client as StorageClient


@lru_cache(maxsize=1)
def get_pubsub_client() -> PublisherClient | None:
    if get_settings().local_mode:
        return None
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


@lru_cache(maxsize=1)
def get_firestore_client() -> FirestoreClient | None:
    settings = get_settings()
    if settings.local_mode:
        return None
    from google.cloud import firestore

    return firestore.Client(project=settings.gcp_project_id)


@lru_cache(maxsize=1)
def get_storage_client() -> StorageClient | None:
    settings = get_settings()
    if settings.local_mode:
        return None
    from google.cloud import storage

    return storage.Client(project=settings.gcp_project_id)


def reset_client_cache() -> None:
    get_pubsub_client.cache_clear()
    get_firestore_client.cache_clear()
    get_storage_client.cache_clear()
