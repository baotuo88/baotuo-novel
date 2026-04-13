# AIMETA P=用户订阅模型_系统Key订阅授权|R=用户订阅状态_套餐有效期|NR=不含计费逻辑|E=UserSubscription|X=internal|A=ORM模型|D=sqlalchemy|S=none|RD=./README.ai
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base


class UserSubscription(Base):
    """用户订阅信息，用于控制是否可使用系统默认 API Key。"""

    __tablename__ = "user_subscriptions"

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    plan_name: Mapped[str] = mapped_column(String(64), nullable=False, default="basic")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship("User", back_populates="subscription")

    def is_active(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.utcnow()
        if self.starts_at and self.starts_at.tzinfo and now.tzinfo is None:
            now = now.replace(tzinfo=self.starts_at.tzinfo)
        if self.expires_at and self.expires_at.tzinfo and now.tzinfo is None:
            now = now.replace(tzinfo=self.expires_at.tzinfo)
        if self.status != "active":
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.expires_at and self.expires_at <= now:
            return False
        return True
