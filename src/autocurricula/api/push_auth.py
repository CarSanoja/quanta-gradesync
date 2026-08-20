import secrets

from fastapi import HTTPException, Request, status

BEARER_SCHEME = "bearer"
PUSH_TOKEN_PARAM = "token"


def extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != BEARER_SCHEME:
        return None
    return token.strip()


def extract_query_token(request: Request) -> str | None:
    token = request.query_params.get(PUSH_TOKEN_PARAM)
    if token is None:
        return None
    stripped = token.strip()
    return stripped or None


def resolve_push_token(request: Request, expected: str) -> str | None:
    query_token = extract_query_token(request)
    if query_token is not None:
        return query_token
    return extract_bearer_token(request)


def require_push_token(request: Request, expected: str) -> None:
    provided = resolve_push_token(request, expected)
    if provided is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing push token query parameter or bearer authorization header",
        )
    if not expected or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="pubsub push verification token rejected",
        )
