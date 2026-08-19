from autocurricula.core.orchestration.context import JobContext, StageStep
from autocurricula.core.telemetry import Recorder, usage_scope
from autocurricula.schemas.telemetry import (
    ATTR_AGENT_STAGE,
    ATTR_GEN_AI_CALLS,
    ATTR_GEN_AI_USAGE_INPUT_TOKENS,
    ATTR_GEN_AI_USAGE_OUTPUT_TOKENS,
    ATTR_GEN_AI_USAGE_TOKENS,
)


async def execute_stage(
    step: StageStep, context: JobContext, recorder: Recorder
) -> JobContext:
    with recorder.span(
        f"Stage_{step.name}",
        stage=step.name.upper(),
        attributes={ATTR_AGENT_STAGE: step.name.upper()},
    ) as span:
        with usage_scope() as ledger:
            result = await step.callable(context)
        span.set(ATTR_GEN_AI_CALLS, ledger.calls)
        span.set(ATTR_GEN_AI_USAGE_INPUT_TOKENS, ledger.input_tokens)
        span.set(ATTR_GEN_AI_USAGE_OUTPUT_TOKENS, ledger.output_tokens)
        span.set(ATTR_GEN_AI_USAGE_TOKENS, ledger.total_tokens)
    return result
