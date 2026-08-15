from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from bearvoice.config import Settings
from bearvoice.security.auth import (
    Principal,
    assert_product_scope,
    get_principal,
    issue_dev_token,
)


async def test_product_manager_cannot_read_another_product_line():
    settings = Settings(
        dev_auth_enabled=True,
        dev_auth_signing_key="test-only-signing-key-at-least-32-bytes",
    )
    app = FastAPI()
    app.state.settings = settings

    @app.get("/products/{product_line}")
    async def product_view(
        product_line: str,
        principal: Principal = Depends(get_principal),
    ):
        assert_product_scope(product_line, principal)
        return {"product_line": product_line}

    token = issue_dev_token(
        settings,
        subject="pm-1",
        roles=("product_manager",),
        product_lines=("养生壶",),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unauthorized = await client.get("/products/养生壶")
        forbidden = await client.get(
            "/products/洗衣机",
            headers={"Authorization": f"Bearer {token}"},
        )
        allowed = await client.get(
            "/products/养生壶",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert unauthorized.status_code == 401
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "无权访问该产品线"
    assert allowed.status_code == 200
