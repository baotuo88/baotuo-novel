# AIMETA P=LLM调用日志模型_调用观测与成本估算|R=调用日志落库|NR=不含业务计算逻辑|E=LLMCallLog|X=internal|A=ORM模型|D=sqlalchemy|S=db|RD=./README.ai
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


# 兼容 SQLite 自增主键
BIGINT_PK_TYPE = BigInteger().with_variant(Integer, "sqlite")


class LLMCallLog(Base):
    """记录每一次 LLM 调用的关键观测指标，用于后台审计与成本分析。"""

    __tablename__ = "llm_call_logs"

    id: Mapped[int] = mapped_column(BIGINT_PK_TYPE, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False, default="chat")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="openai-compatible")
    model: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[Optional[float]] = mapped_column(Float)
    finish_reason: Mapped[Optional[str]] = mapped_column(String(32))
    error_type: Mapped[Optional[str]] = mapped_column(String(64))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
