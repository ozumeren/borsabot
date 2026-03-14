from fastapi import Request, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_security = HTTPBearer(auto_error=False)

_api_key: str = ""


def set_api_key(key: str) -> None:
    global _api_key
    _api_key = key


async def require_auth(request: Request) -> None:
    """Dependency: validates Bearer token. Skip for /health."""
    if request.url.path in ("/health",):
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    token = auth[len("Bearer "):]
    if not _api_key or token != _api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
