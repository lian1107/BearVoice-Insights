from fastapi import APIRouter

from bearvoice.api.routes.admin import router as admin_router
from bearvoice.api.routes.dashboard import router as dashboard_router
from bearvoice.api.routes.evaluation import router as evaluation_router
from bearvoice.api.routes.evidence import router as evidence_router
from bearvoice.api.routes.opportunities import router as opportunities_router
from bearvoice.api.routes.sources import router as sources_router
from bearvoice.api.routes.taxonomy import router as taxonomy_router


api_router = APIRouter(prefix="/api")
api_router.include_router(dashboard_router)
api_router.include_router(evidence_router)
api_router.include_router(sources_router)
api_router.include_router(taxonomy_router)
api_router.include_router(opportunities_router)
api_router.include_router(evaluation_router)
api_router.include_router(admin_router)
