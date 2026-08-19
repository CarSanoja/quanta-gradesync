from fastapi import APIRouter, Depends, HTTPException, Request, status

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.optimizer_history import list_history
from autocurricula.api.optimizer_views import (
    OptimizerReportResponse,
    OptimizerVariantView,
    build_cycles,
    build_variant_view,
    resolve_variant,
)
from autocurricula.api.webhooks import require_push_token

optimizer_router = APIRouter(tags=["optimizer"])


@optimizer_router.get("/optimizer/report", response_model=OptimizerReportResponse)
async def optimizer_report(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> OptimizerReportResponse:
    require_push_token(request, container.settings.pubsub_push_token)
    try:
        records = await list_history(container.settings)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"prompt variant history unavailable: {error}",
        ) from error
    cycles = build_cycles(records)
    variants: list[OptimizerVariantView] = []
    for optimizer in container.optimizers:
        resolved = resolve_variant(optimizer.registry, optimizer.variant_id, records)
        if resolved is None:
            continue
        variant, source = resolved
        variants.append(build_variant_view(variant, source, cycles))
    return OptimizerReportResponse(
        variants=variants, cycles=cycles, cycle_count=len(cycles)
    )
