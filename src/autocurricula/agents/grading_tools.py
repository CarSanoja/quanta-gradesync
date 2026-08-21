from typing import Any

from autocurricula.config.settings import Settings
from autocurricula.core.armor.metadata import safe_identifier, safe_path
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.tools.base import as_function_tool
from autocurricula.tools.gcs_fetcher import fetch_exam_files as stage_batch_files
from autocurricula.tools.vector_search import (
    DEFAULT_TOP_K,
    MemoryVectorProvider,
)
from autocurricula.tools.vector_search import (
    search_rubrics as retrieve_rubric_passages,
)


def prompt_safe_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    files = result.get("payload", {}).get("files")
    if not isinstance(files, dict):
        return result
    result["payload"]["files"] = {
        safe_identifier(submission_id): [safe_path(path) for path in paths]
        for submission_id, paths in files.items()
    }
    return result


def build_grading_tools(settings: Settings) -> list[Any]:
    async def fetch_exam_files(batch: dict[str, Any]) -> dict[str, Any]:
        """Stage the exam files of a batch on local disk and return their local paths.

        Args:
            batch: exam batch object carrying job_id, class_id, subject, grade_level,
                rubric_id and the list of submissions to stage.

        Returns:
            Tool result with ok, error and a payload holding the staged local paths.
        """
        result = await stage_batch_files(batch)
        return prompt_safe_tool_result(result.model_dump(mode="json"))

    async def search_rubrics(
        query: str, subject: str = "", top_k: int = DEFAULT_TOP_K
    ) -> dict[str, Any]:
        """Retrieve rubric and curriculum passages related to a semantic query.

        Args:
            query: natural language description of the rubric material needed.
            subject: optional subject label used to focus the search.
            top_k: maximum number of passages to return.

        Returns:
            Retrieved context object with the resolved query and the matching chunks.
        """
        provider = MemoryVectorProvider(memory=MemoryManager.from_settings(settings))
        context = await retrieve_rubric_passages(
            query, subject=subject, top_k=top_k, provider=provider
        )
        return context.model_dump(mode="json")

    return [as_function_tool(fetch_exam_files), as_function_tool(search_rubrics)]
