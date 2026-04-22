import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import dependencies
from app.services.auth_service import AuthService


async def _assert_get_current_admin_blocks_default_password_admin():
    current_user = SimpleNamespace(is_admin=True, must_change_password=True)

    with pytest.raises(HTTPException) as exc_info:
        await dependencies.get_current_admin(current_user)

    assert exc_info.value.status_code == 403
    assert "请先修改密码" in exc_info.value.detail


async def _assert_get_current_admin_allows_normal_admin():
    current_user = SimpleNamespace(is_admin=True, must_change_password=False)

    resolved = await dependencies.get_current_admin(current_user)

    assert resolved is current_user


async def _assert_resolve_linuxdo_username_adds_suffix_on_conflict():
    service = AuthService(session=None)
    service.user_repo = SimpleNamespace()

    existing = {
        "alice": SimpleNamespace(external_id=None),
        "alice_12345678": None,
    }

    async def get_by_username(username: str):
        return existing.get(username)

    service.user_repo.get_by_username = get_by_username

    resolved = await service._resolve_linuxdo_username("linuxdo:abc12345678", "alice")

    assert resolved == "alice_12345678"


def test_get_current_admin_blocks_default_password_admin_sync():
    asyncio.run(_assert_get_current_admin_blocks_default_password_admin())


def test_get_current_admin_allows_normal_admin_sync():
    asyncio.run(_assert_get_current_admin_allows_normal_admin())


def test_resolve_linuxdo_username_adds_suffix_on_conflict_sync():
    asyncio.run(_assert_resolve_linuxdo_username_adds_suffix_on_conflict())
