"""One place that decides whether a request may reach the application.

Every route used to remember to call require_push_token itself. That worked, but
it left two holes: a new route only had to forget, and an unauthenticated caller
could still make FastAPI validate a body first and read the schema back out of
the 422. /openapi.json was open too, which handed over the whole surface.

The allowlist is deliberately short. It is the shells a person needs before they
can type the code, and the health check Cloud Run polls.
"""

import secrets
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from autocurricula.api.dependencies import CONTAINER_STATE_KEY
from autocurricula.api.push_auth import resolve_push_token

# Static pages carry no data: they render, then ask for the code. Serving them
# unauthenticated is what makes the code enterable at all.
PUBLIC_EXACT = frozenset({"/", "/teacher", "/console", "/readyz", "/healthz"})
PUBLIC_PREFIXES = ("/teacher/assets/", "/console/assets/", "/console/diagrams/")

UNAUTHORIZED = "missing access code: send it as a bearer token or a token query parameter"
REJECTED = "access code rejected"


def is_public(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def secret_of(request: Request) -> str:
    container = getattr(request.app.state, CONTAINER_STATE_KEY, None)
    if container is None:
        return ""
    return container.settings.pubsub_push_token or ""


def build_gate() -> Callable:
    """The secret is read per request, from the container the lifespan installed."""

    async def gate(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method == "OPTIONS" or is_public(request.url.path):
            return await call_next(request)
        secret = secret_of(request)
        provided = resolve_push_token(request, secret)
        if provided is None:
            return JSONResponse({"detail": UNAUTHORIZED}, status_code=401)
        # A deployment with no secret configured admits nobody, which is what
        # local mode already did; a configured one is compared in constant time.
        if not secret or not secrets.compare_digest(
            provided.encode("utf-8"), secret.encode("utf-8")
        ):
            return JSONResponse({"detail": REJECTED}, status_code=403)
        return await call_next(request)

    return gate
