# AIMETA P=用户订阅服务_订阅查询和管理|R=订阅状态判断_管理员设置|NR=不含支付网关|E=UserSubscriptionService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
import json
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import UserSubscription, UserSubscriptionAuditLog
from ..repositories.user_repository import UserRepository
from ..repositories.user_subscription_repository import UserSubscriptionRepository
from ..schemas.user import UserSubscriptionAuditRead, UserSubscriptionRead, UserSubscriptionUpsert


class UserSubscriptionService:
    """用户订阅服务，提供状态查询与管理员配置入口。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.subscription_repo = UserSubscriptionRepository(session)

    def _to_read(self, item: Optional[UserSubscription], user_id: int) -> UserSubscriptionRead:
        if item is None:
            return UserSubscriptionRead(
                user_id=user_id,
                plan_name="free",
                status="inactive",
                starts_at=None,
                expires_at=None,
                is_active=False,
            )
        return UserSubscriptionRead(
            user_id=item.user_id,
            plan_name=item.plan_name,
            status=item.status,
            starts_at=item.starts_at,
            expires_at=item.expires_at,
            is_active=item.is_active(),
        )

    @staticmethod
    def _snapshot(item: Optional[UserSubscription], user_id: int) -> dict:
        if item is None:
            return {
                "user_id": user_id,
                "plan_name": "free",
                "status": "inactive",
                "starts_at": None,
                "expires_at": None,
            }
        return {
            "user_id": item.user_id,
            "plan_name": item.plan_name,
            "status": item.status,
            "starts_at": item.starts_at.isoformat() if item.starts_at else None,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        }

    async def get_user_subscription(self, user_id: int) -> UserSubscriptionRead:
        user = await self.user_repo.get(id=user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        item = await self.subscription_repo.get_by_user_id(user_id)
        return self._to_read(item, user_id)

    async def upsert_user_subscription(
        self,
        user_id: int,
        payload: UserSubscriptionUpsert,
        *,
        actor_user_id: Optional[int] = None,
        actor_username: str = "system",
    ) -> UserSubscriptionRead:
        user = await self.user_repo.get(id=user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        starts_at = payload.starts_at
        expires_at = payload.expires_at
        if starts_at and expires_at and expires_at <= starts_at:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="到期时间必须晚于开始时间")

        item = await self.subscription_repo.get_by_user_id(user_id)
        before_snapshot = self._snapshot(item, user_id)
        if item is None:
            item = UserSubscription(
                user_id=user_id,
                plan_name=payload.plan_name,
                status=payload.status,
                starts_at=starts_at or datetime.utcnow(),
                expires_at=expires_at,
            )
            self.session.add(item)
        else:
            item.plan_name = payload.plan_name
            item.status = payload.status
            item.starts_at = starts_at or item.starts_at or datetime.utcnow()
            item.expires_at = expires_at

        after_snapshot = self._snapshot(item, user_id)
        self.session.add(
            UserSubscriptionAuditLog(
                user_id=user_id,
                admin_user_id=actor_user_id,
                admin_username=actor_username,
                action="upsert",
                old_snapshot=json.dumps(before_snapshot, ensure_ascii=False),
                new_snapshot=json.dumps(after_snapshot, ensure_ascii=False),
            )
        )
        await self.session.commit()
        return self._to_read(item, user_id)

    async def has_active_subscription(self, user_id: int) -> bool:
        item = await self.subscription_repo.get_by_user_id(user_id)
        return bool(item and item.is_active())

    async def list_audit_logs(self, *, user_id: Optional[int] = None, limit: int = 100) -> list[UserSubscriptionAuditRead]:
        stmt = select(UserSubscriptionAuditLog)
        if user_id is not None:
            stmt = stmt.where(UserSubscriptionAuditLog.user_id == user_id)
        stmt = stmt.order_by(UserSubscriptionAuditLog.created_at.desc()).limit(max(1, min(limit, 500)))
        rows = (await self.session.execute(stmt)).scalars().all()
        return [UserSubscriptionAuditRead.model_validate(row) for row in rows]
