import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router
from app.core.config import settings

logger = structlog.get_logger()

app = FastAPI(title="SeenBy API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
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
    return {"status": "ok"}
