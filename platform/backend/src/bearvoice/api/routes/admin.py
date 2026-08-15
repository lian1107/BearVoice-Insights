from fastapi import APIRouter, Depends, Request

from bearvoice.config import Settings
from bearvoice.domain.enums import Permission
from bearvoice.security.auth import Principal, require_permission


router = APIRouter(tags=["admin"])


@router.get("/admin/status")
async def admin_status(
    request: Request,
    _principal: Principal = Depends(require_permission(Permission.ADMIN)),
) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    return {
        "oidc_configured": bool(
            settings.oidc_issuer
            and settings.oidc_audience
            and settings.oidc_jwks_url
        ),
        "dev_auth_enabled": settings.dev_auth_enabled,
        "model_egress_enabled": settings.model_egress_enabled,
        "approved_model_providers": list(settings.model_provider_allowlist),
        "approved_model_purposes": list(settings.model_purpose_allowlist),
        "data_retention_days": settings.data_retention_days,
    }
