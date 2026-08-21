from pathlib import Path
from typing import Any

SIDECAR_SUFFIX = ".txt"


class RawSidecarProvider:
    def __init__(self, texts: dict[tuple[str, int], str]) -> None:
        self._texts = dict(texts)

    def page_text(self, submission_id: str, page: int) -> str | None:
        return self._texts.get((submission_id, page))


def raw_sidecar_texts(batch: Any) -> dict[tuple[str, int], str]:
    texts: dict[tuple[str, int], str] = {}
    for submission in batch.submissions:
        for exam_file in submission.files:
            if exam_file.local_path is None:
                continue
            sidecar = Path(exam_file.local_path).with_suffix(SIDECAR_SUFFIX)
            if not sidecar.is_file():
                continue
            content = sidecar.read_text(encoding="utf-8")
            for page in range(1, max(1, exam_file.page_count) + 1):
                texts[(submission.submission_id, page)] = content
    return texts


def raw_provider_for(batch: Any) -> RawSidecarProvider:
    return RawSidecarProvider(raw_sidecar_texts(batch))
