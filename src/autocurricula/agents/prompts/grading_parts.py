import json
from typing import Any

from autocurricula.agents.base import inline_file_part, text_part
from autocurricula.agents.prompts.feedback_bands import band_task_block
from autocurricula.core.armor.metadata import prompt_safe_submission, safe_path
from autocurricula.schemas.exam import ExamSubmission
from autocurricula.schemas.feedback import FeedbackBand
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import Rubric

MAX_INLINE_FILE_BYTES = 18 * 1024 * 1024


async def build_grading_parts(
    submission: ExamSubmission,
    rubric: Rubric,
    context: RetrievedContext,
    *,
    max_inline_bytes: int = MAX_INLINE_FILE_BYTES,
    band: FeedbackBand | None = None,
) -> list[Any]:
    task = {
        "submission": prompt_safe_submission(submission),
        "rubric": rubric.model_dump(mode="json"),
        "retrieved_context": context.model_dump(mode="json"),
    }
    payload = json.dumps(task, ensure_ascii=False, indent=2)
    parts = [text_part(f"GRADE THIS SUBMISSION\n{payload}")]
    if band is not None:
        parts.append(text_part(band_task_block(band)))
    notes: list[str] = []
    for file in submission.files:
        safe_uri = safe_path(file.gcs_uri)
        if file.local_path is None:
            notes.append(f"{safe_uri}: not staged inline; call fetch_exam_files")
            continue
        part = await inline_file_part(
            file.local_path, file.mime_type, max_bytes=max_inline_bytes
        )
        if part is None:
            notes.append(f"{safe_uri}: exceeds inline byte limit; call fetch_exam_files")
        else:
            parts.append(part)
    if notes:
        parts.append(text_part("File notes:\n" + "\n".join(notes)))
    return parts
