import hashlib
import re

HEX_32 = re.compile(r"^[0-9a-f]{32}$")

TRACE_EXPLORER_URL = (
    "https://console.cloud.google.com/traces/list?project={project}&tid={trace_id}"
)


def cloud_trace_id(trace_id: str) -> str:
    normalized = trace_id.strip().lower()
    if HEX_32.fullmatch(normalized):
        return normalized
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def cloud_trace_url(project_id: str, trace_id: str) -> str | None:
    if not project_id or not trace_id:
        return None
    return TRACE_EXPLORER_URL.format(
        project=project_id, trace_id=cloud_trace_id(trace_id)
    )
