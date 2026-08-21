from fastapi import APIRouter, Depends, HTTPException, Request, status

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.fleet import build_fleet_registry
from autocurricula.schemas.fleet import FleetRegistryResponse

fleet_router = APIRouter(tags=["fleet"])


@fleet_router.get("/fleet/registry", response_model=FleetRegistryResponse)
async def fleet_registry(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> FleetRegistryResponse:
    require_push_token(request, container.settings.pubsub_push_token)
    try:
        return build_fleet_registry(container.settings, container)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"fleet registry could not be derived: {error}",
        ) from error
