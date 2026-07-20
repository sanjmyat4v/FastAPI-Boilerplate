import logging
import uuid
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.database import init_db, close_db
from app.core.error_handler import register_exception_handlers
from app.core.redis_client import init_redis, close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "App starting up (env=%s, version=%s)",
        settings.app_env,
        settings.app_version
    )

    # --------------------------------------------
    # Startup
    # --------------------------------------------
    try:
        # 1. Database engines.
        init_db()
        logger.info("Database engine pool initialised.")

        # 2. Redis pool.
        init_redis()
        logger.info("Redis connection pool initialised.")
    except Exception as exc:
        logger.critical(
            "Fatal error during startup - application cannot start: %s",
            exc,
            exc_info=True,
        )
        raise

    logger.info("App startup complete. Accepting requests.")

    # ------------------------------------------------------------------
    # Application runs here.
    # ------------------------------------------------------------------
    yield

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    logger.info("App shutting down...")

    try:
        await close_redis()
    except Exception as exc:
        logger.error("Error closing Redis pool: %s", exc, exc_info=True)
    
    try:
        await close_db()
    except Exception as exc:
        logger.error("Error closing DB engine pool: %s", exc, exc_info=True)
    
    logger.info("App shutdown complete")

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="FastAPI app Boilerplate",
        description="Fastapi backend boilerplate",
        version=settings.app_version,
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        openapi_url="/openapi.json" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    # --------------------------------------
    # Middleware
    # --------------------------------------
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    
    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # Skip health check logging to reduce probe noise.
        if not request.url.path.endswith("/health"):
            logger.info(
                "%s %s → %d (%.1fms) request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                getattr(request.state, "request_id", "-"),
            )
        return response
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    # ------------------------------------------------------------------
    # Exception Handlers
    # ------------------------------------------------------------------
    register_exception_handlers(app)

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    app.include_router(api_v1_router)

    # ------------------------------------------------------------------
    # Root redirect — helpful for developers hitting the bare host.
    # Only active in non-production environments.
    # ------------------------------------------------------------------
    if settings.app_env != "production":
        @app.get("/", include_in_schema=False)
        async def root():
            return JSONResponse(
                content={
                    "service": "FastAPI boilerplate",
                    "version": settings.app_version,
                    "docs": "/docs",
                    "health": "/api/v1/health",
                }
            )
    
    return app

app = create_app()