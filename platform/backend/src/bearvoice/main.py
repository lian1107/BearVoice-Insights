import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from bearvoice.api.router import api_router
from bearvoice.config import Settings
from bearvoice.db import create_database_engine, create_session_factory
from bearvoice.security.local_session import LocalDevSessionStore


def create_app(settings: Settings | None = None) -> FastAPI:
    active = settings or Settings()
    database_engine = create_database_engine(active)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        await database_engine.dispose()

    production = active.runtime_environment == "production"
    app = FastAPI(
        title="BearVoice",
        version="0.1.0",
        docs_url=None if production else "/api/docs",
        redoc_url=None,
        openapi_url=None if production else "/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = active
    app.state.local_dev_sessions = LocalDevSessionStore()
    app.state.db_engine = database_engine
    app.state.db_session_factory = create_session_factory(database_engine)
    app.include_router(api_router)

    @app.middleware("http")
    async def secure_api_responses(request: Request, call_next):
        request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "service": "bearvoice",
            "status": "ok",
            "model_egress": (
                "enabled" if active.model_egress_enabled else "disabled"
            ),
        }

    @app.get("/api/ready")
    async def readiness() -> JSONResponse:
        issues = list(active.production_readiness_issues())
        try:
            async with database_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except Exception:
            issues.append("database is unavailable")
        ready = not issues
        return JSONResponse(
            status_code=(
                status.HTTP_200_OK
                if ready
                else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            content={
                "service": "bearvoice",
                "status": "ready" if ready else "not_ready",
                "checks": issues,
            },
            headers={"Cache-Control": "no-store"},
        )

    return app


app = create_app()
