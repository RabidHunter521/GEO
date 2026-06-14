import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import router
from app.core.config import settings
from app.core.database import engine
from app.core.logging import configure_logging

configure_logging()
logger = structlog.get_logger()

app = FastAPI(title="SeenBy API", version="0.1.0")


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Tag every request with an id (honoring an inbound X-Request-ID), bind it
    to the log context so all logs in the request carry it, and emit one access
    line with status + duration. The id is echoed back in the response header."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - start) * 1000, 1),
    )
    structlog.contextvars.clear_contextvars()
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    # Auth is a bearer token, not cookies — credentials aren't needed, and
    # disabling them avoids the credentialed-CORS + wildcard pitfalls.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all so unhandled errors return a uniform JSON shape (matching
    FastAPI's `detail` envelope) and are logged with request context — never a
    leaked stack trace."""
    logger.error(
        "unhandled_exception",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(router)


@app.get("/health")
def health():
    """Liveness — the process is up. Cheap; no dependencies touched."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness():
    """Readiness — can we actually reach the database?"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:
        logger.warning("readiness_check_failed", error=str(exc))
        return JSONResponse(status_code=503, content={"status": "not ready"})
