# AIMETA P=订阅审计日志模型_管理员订阅变更留痕|R=记录前后变更与操作者|NR=不含业务逻辑|E=UserSubscriptionAuditLog|X=internal|A=ORM模型|D=sqlalchemy|S=none|RD=./README.ai
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class UserSubscriptionAuditLog(Base):
    """用户订阅变更审计日志。"""

    __tablename__ = "user_subscription_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    admin_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_username: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="upsert")
    old_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    new_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
