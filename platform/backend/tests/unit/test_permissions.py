import pytest
from fastapi import HTTPException

from bearvoice.domain.enums import Permission
from bearvoice.security.auth import (
    Principal,
    assert_permission,
    assert_product_scope,
)


def test_product_manager_has_role_permissions_but_not_global_scope():
    principal = Principal.from_claims(
        {
            "sub": "pm-1",
            "roles": ["product_manager"],
            "product_lines": ["养生壶"],
        }
    )

    assert_permission(principal, Permission.READ_VOICE)
    assert_permission(principal, Permission.REVIEW_OPPORTUNITY)
    assert_product_scope("养生壶", principal)
    with pytest.raises(HTTPException) as permission_error:
        assert_permission(principal, Permission.ADMIN)
    with pytest.raises(HTTPException) as scope_error:
        assert_product_scope("洗衣机", principal)

    assert permission_error.value.status_code == 403
    assert scope_error.value.status_code == 403
    assert scope_error.value.detail == "无权访问该产品线"


def test_source_admin_can_manage_sources_and_run_analysis():
    principal = Principal.from_claims(
        {
            "sub": "source-operator-1",
            "roles": ["source_admin"],
            "product_lines": ["养生壶"],
        }
    )

    assert_permission(principal, Permission.MANAGE_SOURCES)
    assert_permission(principal, Permission.RUN_ANALYSIS)
