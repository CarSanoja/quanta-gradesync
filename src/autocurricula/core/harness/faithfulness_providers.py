from autocurricula.core.harness.faithfulness import PageTextProvider, normalize_text

SOURCE_SIDECAR = "sidecar"
SOURCE_TRANSCRIPT = "transcript"


class SidecarTextProvider:
    match_threshold: float | None = None

    def __init__(self, texts: dict[tuple[str, int], str]) -> None:
        self._texts = {
            (submission_id, page): normalize_text(text)
            for (submission_id, page), text in texts.items()
        }

    def page_text(self, submission_id: str, page: int) -> str | None:
        return self._texts.get((submission_id, page))


class TranscriptTextProvider:
    def __init__(
        self,
        texts: dict[tuple[str, int], str],
        match_threshold: float | None = None,
    ) -> None:
        self._texts = {
            (submission_id, page): normalize_text(text)
            for (submission_id, page), text in texts.items()
        }
        self.match_threshold = match_threshold

    def page_text(self, submission_id: str, page: int) -> str | None:
        return self._texts.get((submission_id, page))


class CompositeTextProvider:
    def __init__(
        self, primary: PageTextProvider, fallback: PageTextProvider
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def match_threshold(self) -> float | None:
        return getattr(self._fallback, "match_threshold", None)

    def page_text(self, submission_id: str, page: int) -> str | None:
        primary = self._primary.page_text(submission_id, page)
        if primary is not None:
            return primary
        return self._fallback.page_text(submission_id, page)

    def source_for(self, submission_id: str, page: int) -> str | None:
        if self._primary.page_text(submission_id, page) is not None:
            return SOURCE_SIDECAR
        if self._fallback.page_text(submission_id, page) is not None:
            return SOURCE_TRANSCRIPT
        return None

    def threshold_for(self, submission_id: str, page: int) -> float | None:
        if self.source_for(submission_id, page) == SOURCE_TRANSCRIPT:
            return self.match_threshold
        return None
