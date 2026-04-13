# AIMETA P=用户订阅仓库_订阅数据访问|R=按用户查询订阅|NR=不含业务逻辑|E=UserSubscriptionRepository|X=internal|A=仓库类|D=sqlalchemy|S=db|RD=./README.ai
from typing import Optional

from sqlalchemy import select

from .base import BaseRepository
from ..models import UserSubscription


class UserSubscriptionRepository(BaseRepository[UserSubscription]):
    model = UserSubscription

    async def get_by_user_id(self, user_id: int) -> Optional[UserSubscription]:
        stmt = select(UserSubscription).where(UserSubscription.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()
