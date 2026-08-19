from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GRADESYNC_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gcp_project_id: str = ""
    gcp_region: str = "us-central1"

    gemini_pro_model: str = "gemini-3.5-pro"
    gemini_flash_model: str = "gemini-3.5-flash"
    embedding_model: str = "text-embedding-005"

    pubsub_topic: str = ""
    pubsub_push_token: str = ""

    gcs_bucket: str = ""
    gcs_local_staging_dir: Path = Path(".staging")

    firestore_jobs_collection: str = "jobs"
    firestore_checkpoints_collection: str = "checkpoints"
    firestore_profiles_collection: str = "profiles"
    firestore_competencies_collection: str = "competencies"
    firestore_prompts_collection: str = "prompts"
    firestore_reviews_collection: str = "reviews"

    confidence_threshold: float = Field(default=0.85, gt=0.0, le=1.0)
    optimizer_candidates: int = Field(default=3, ge=1, le=8)
    optimizer_max_cycles: int = Field(default=3, ge=1, le=10)
    optimizer_convergence_min_improvement: float = Field(default=0.01, ge=0.0)
    verify_max_iterations: int = Field(default=2, ge=0, le=5)

    harness_max_calls_per_item: int = Field(default=4, ge=1, le=16)
    schema_repair_attempts: int = Field(default=2, ge=0, le=5)
    batch_anomaly_threshold: float = Field(default=0.15, gt=0.0, le=1.0)
    variance_collapse_ratio: float = Field(default=0.20, gt=0.0, le=1.0)
    objective_gate_enabled: bool = True
    objective_qwk_min: float = Field(default=0.85, ge=-1.0, le=1.0)
    objective_mae_max: float = Field(default=0.4, gt=0.0)
    objective_bias_abs_max: float = Field(default=0.1, gt=0.0)

    model_fallback_latency_seconds: float = Field(default=15.0, gt=0.0)
    model_fallback_confidence_factor: float = Field(default=0.9, gt=0.0, le=1.0)
    dead_letter_max_attempts: int = Field(default=3, ge=1, le=10)
    telemetry_audit_enabled: bool = True
    firestore_audit_collection: str = "audit"
    firestore_dead_letter_collection: str = "dead_letter"

    sis_base_url: str = ""
    sis_api_token: str = ""

    local_mode: bool = True
    local_data_dir: Path = Path(".local_data")

    api_host: str = "0.0.0.0"
    api_port: int = 8080

    @model_validator(mode="before")
    @classmethod
    def _default_local_mode(cls, values: Any) -> Any:
        if isinstance(values, dict) and "local_mode" not in values:
            values["local_mode"] = not bool(values.get("gcp_project_id"))
        return values

    @property
    def is_gcp_configured(self) -> bool:
        return bool(self.gcp_project_id)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
