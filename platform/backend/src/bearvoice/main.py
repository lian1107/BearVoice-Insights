from fastapi import FastAPI

from bearvoice.api.router import api_router
from bearvoice.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    active = settings or Settings()
    app = FastAPI(title="BearVoice", version="0.1.0")
    app.state.settings = active
    app.include_router(api_router)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "service": "bearvoice",
            "status": "ok",
            "model_egress": (
                "enabled" if active.model_egress_enabled else "disabled"
            ),
        }

    return app


app = create_app()
