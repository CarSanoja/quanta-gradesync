from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

GCP_SETTLE_INTERVAL_SECONDS = 5.0
FALSE_TOKENS = frozenset({"false", "0", "no", "off"})


def _is_local(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in FALSE_TOKENS
    return bool(value)


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

    gemini_pro_model: str = "gemini-3.5-flash"
    gemini_flash_model: str = "gemini-3.5-flash-lite"
    embedding_model: str = "text-embedding-005"
    gemini_location: str = "global"

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

    armor_enabled: bool = True
    faithfulness_transcription_enabled: bool = True
    faithfulness_match_threshold: float = Field(default=0.75, gt=0.0, le=1.0)
    legibility_enabled: bool = True
    legibility_full_trust: float = Field(default=0.70, gt=0.0, le=1.0)
    legibility_confidence_floor: float = Field(default=0.50, gt=0.0, le=1.0)

    model_fallback_latency_seconds: float = Field(default=90.0, gt=0.0)
    model_fallback_confidence_factor: float = Field(default=0.9, gt=0.0, le=1.0)
    dead_letter_max_attempts: int = Field(default=3, ge=1, le=10)
    telemetry_audit_enabled: bool = True
    telemetry_live_enabled: bool = True
    telemetry_cloud_trace_enabled: bool = True
    telemetry_cloud_metrics_enabled: bool = True
    telemetry_capture_content: bool = True
    telemetry_payload_max_chars: int = Field(default=4000, ge=200, le=20000)
    log_json: bool | None = None
    firestore_audit_collection: str = "audit"
    firestore_dead_letter_collection: str = "dead_letter"

    sis_base_url: str = ""
    sis_api_token: str = ""
    sis_audience: str = ""

    runtime_service_account: str = ""
    sis_writer_service_account: str = ""
    agent_impersonation_enabled: bool = False
    agent_impersonation_lifetime_seconds: int = Field(default=3600, ge=60, le=43200)

    gemma_model: str = "gemma-4-31b-it"
    gemma_api_key: str = ""

    resume_stale_after_seconds: float = Field(default=600.0, gt=0.0)
    batch_settle_interval_seconds: float = Field(default=0.0, ge=0.0, le=120.0)
    batch_settle_max_rounds: int = Field(default=6, ge=1, le=60)

    local_mode: bool = True
    local_data_dir: Path = Path(".local_data")

    api_host: str = "0.0.0.0"
    api_port: int = 8080

    @model_validator(mode="before")
    @classmethod
    def _default_local_mode(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        if "local_mode" not in values:
            values["local_mode"] = not bool(values.get("gcp_project_id"))
        if _is_local(values.get("local_mode")):
            return values
        if "batch_settle_interval_seconds" not in values:
            values["batch_settle_interval_seconds"] = GCP_SETTLE_INTERVAL_SECONDS
        return values

    @property
    def is_gcp_configured(self) -> bool:
        return bool(self.gcp_project_id)

    @property
    def resolved_log_json(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return not self.local_mode


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
