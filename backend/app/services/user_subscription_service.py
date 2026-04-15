# AIMETA P=用户订阅服务_订阅查询和管理|R=订阅状态判断_管理员设置|NR=不含支付网关|E=UserSubscriptionService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import LLMCallLog, SystemConfig, UserDailyRequest, UserSubscription, UserSubscriptionAuditLog
from ..services.admin_setting_service import AdminSettingService
from ..repositories.user_repository import UserRepository
from ..repositories.user_subscription_repository import UserSubscriptionRepository
from ..schemas.user import (
    UserSubscriptionAuditRead,
    UserSubscriptionBillingItemRead,
    UserSubscriptionBillingSummaryRead,
    UserSubscriptionCompensationRead,
    UserSubscriptionRead,
    UserSubscriptionUpsert,
    UserSubscriptionUsageSummaryRead,
)

logger = logging.getLogger(__name__)


class UserSubscriptionService:
    """用户订阅服务，提供状态查询与管理员配置入口。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.subscription_repo = UserSubscriptionRepository(session)
        self.admin_setting_service = AdminSettingService(session)

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
        item = await self._auto_degrade_if_expired(item, user_id=user_id)
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
        item = await self._auto_degrade_if_expired(item, user_id=user_id)
        return bool(item and item.is_active())

    async def list_audit_logs(self, *, user_id: Optional[int] = None, limit: int = 100) -> list[UserSubscriptionAuditRead]:
        stmt = select(UserSubscriptionAuditLog)
        if user_id is not None:
            stmt = stmt.where(UserSubscriptionAuditLog.user_id == user_id)
        stmt = stmt.order_by(UserSubscriptionAuditLog.created_at.desc()).limit(max(1, min(limit, 500)))
        rows = (await self.session.execute(stmt)).scalars().all()
        return [UserSubscriptionAuditRead.model_validate(row) for row in rows]

    async def _auto_degrade_if_expired(
        self,
        item: Optional[UserSubscription],
        *,
        user_id: int,
    ) -> Optional[UserSubscription]:
        if not item or item.status != "active" or not item.expires_at:
            return item

        now = datetime.utcnow()
        expires_at = item.expires_at
        if expires_at.tzinfo and now.tzinfo is None:
            now = now.replace(tzinfo=expires_at.tzinfo)
        if expires_at > now:
            return item

        before_snapshot = self._snapshot(item, user_id)
        item.status = "inactive"
        item.plan_name = "free"
        after_snapshot = self._snapshot(item, user_id)
        self.session.add(
            UserSubscriptionAuditLog(
                user_id=user_id,
                admin_user_id=None,
                admin_username="system",
                action="auto_degrade_expired",
                old_snapshot=json.dumps(before_snapshot, ensure_ascii=False),
                new_snapshot=json.dumps(after_snapshot, ensure_ascii=False),
            )
        )
        await self.session.commit()
        return item

    async def _get_system_config_value(self, key: str) -> Optional[str]:
        record = await self.session.execute(select(SystemConfig.value).where(SystemConfig.key == key))
        value = record.scalar_one_or_none()
        return value

    @staticmethod
    def _parse_positive_float(raw_value: Optional[str], default: float = 0.0) -> float:
        if raw_value in (None, ""):
            return default
        try:
            return max(0.0, float(str(raw_value).strip()))
        except Exception:
            return default

    @staticmethod
    def _parse_thresholds(raw_value: Optional[str]) -> tuple[float, float]:
        values: list[float] = []
        if raw_value:
            for item in str(raw_value).split(","):
                item = item.strip()
                if not item:
                    continue
                try:
                    number = float(item)
                except Exception:
                    continue
                if number <= 0:
                    continue
                values.append(number)
        values = sorted(values)
        if not values:
            return 0.5, 0.8
        warning = values[0]
        critical = values[1] if len(values) > 1 else max(0.8, warning)
        if critical < warning:
            critical = warning
        return warning, critical

    @staticmethod
    def _ratio_level(ratio: float, warning: float, critical: float) -> str:
        if ratio >= 1.0:
            return "exceeded"
        if ratio >= critical:
            return "critical"
        if ratio >= warning:
            return "warning"
        return "ok"

    @staticmethod
    def _merge_warning_level(left: str, right: str) -> str:
        order = {"ok": 0, "warning": 1, "critical": 2, "exceeded": 3}
        return left if order.get(left, 0) >= order.get(right, 0) else right

    async def _resolve_daily_request_limit(self, user_id: int, subscription: Optional[UserSubscription]) -> int:
        raw_default = await self.admin_setting_service.get("daily_request_limit", "100")
        try:
            default_limit = int(str(raw_default or "100").strip())
        except Exception:
            default_limit = 100

        item = subscription
        if item is None:
            item = await self.subscription_repo.get_by_user_id(user_id)
            item = await self._auto_degrade_if_expired(item, user_id=user_id)

        if item and item.is_active(datetime.utcnow()):
            plan_name = (item.plan_name or "").strip()
            if plan_name:
                key = f"subscription.plan.{plan_name}.daily_request_limit"
                raw_limit = await self._get_system_config_value(key)
                if raw_limit not in (None, ""):
                    try:
                        parsed = int(str(raw_limit).strip())
                        if parsed == -1 or parsed >= 0:
                            return parsed
                    except Exception:
                        logger.warning(
                            "套餐请求上限配置非法，按订阅无限处理：user_id=%s plan=%s key=%s value=%s",
                            user_id,
                            plan_name,
                            key,
                            raw_limit,
                        )
            # 订阅生效期内默认无限请求；如需限制，请配置套餐 daily_request_limit。
            return -1

        return max(0, default_limit)

    async def _resolve_daily_budget_limit_usd(self, user_id: int, subscription: Optional[UserSubscription]) -> float:
        # 优先级：用户覆盖 > 套餐预算 > 用户默认预算
        raw_user_override = await self._get_system_config_value(f"llm.budget.daily_usd.user.{user_id}")
        if raw_user_override not in (None, ""):
            return self._parse_positive_float(raw_user_override, default=0.0)

        item = subscription
        if item is None:
            item = await self.subscription_repo.get_by_user_id(user_id)
            item = await self._auto_degrade_if_expired(item, user_id=user_id)

        if item and item.is_active(datetime.utcnow()):
            plan_name = (item.plan_name or "").strip()
            if plan_name:
                raw_plan_budget = await self._get_system_config_value(
                    f"subscription.plan.{plan_name}.daily_budget_usd"
                )
                if raw_plan_budget not in (None, ""):
                    return self._parse_positive_float(raw_plan_budget, default=0.0)

        raw_default = await self._get_system_config_value("llm.budget.daily_usd.user.default")
        return self._parse_positive_float(raw_default, default=0.0)

    async def get_usage_summary(self, user_id: int) -> UserSubscriptionUsageSummaryRead:
        user = await self.user_repo.get(id=user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        subscription = await self.subscription_repo.get_by_user_id(user_id)
        subscription = await self._auto_degrade_if_expired(subscription, user_id=user_id)
        basic = self._to_read(subscription, user_id)

        daily_request_used = await self.user_repo.get_daily_request(user_id)
        daily_request_limit = await self._resolve_daily_request_limit(user_id, subscription)
        daily_request_ratio = (
            round(daily_request_used / daily_request_limit, 6)
            if daily_request_limit > 0
            else 0.0
        )

        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_estimated_cost_usd = float(
            await self.session.scalar(
                select(func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0)).where(
                    LLMCallLog.user_id == user_id,
                    LLMCallLog.status == "success",
                    LLMCallLog.created_at >= day_start,
                )
            )
            or 0.0
        )
        today_estimated_cost_usd = round(today_estimated_cost_usd, 6)

        daily_budget_limit_usd = await self._resolve_daily_budget_limit_usd(user_id, subscription)
        daily_budget_ratio = (
            round(today_estimated_cost_usd / daily_budget_limit_usd, 6)
            if daily_budget_limit_usd > 0
            else 0.0
        )

        warning_raw = await self._get_system_config_value("llm.budget.alert.thresholds")
        warning_threshold, critical_threshold = self._parse_thresholds(warning_raw)
        warning_level = self._ratio_level(daily_request_ratio, warning_threshold, critical_threshold)
        warning_level = self._merge_warning_level(
            warning_level,
            self._ratio_level(daily_budget_ratio, warning_threshold, critical_threshold),
        )

        return UserSubscriptionUsageSummaryRead(
            user_id=user_id,
            plan_name=basic.plan_name,
            status=basic.status,
            is_active=basic.is_active,
            daily_request_used=daily_request_used,
            daily_request_limit=daily_request_limit,
            daily_request_ratio=daily_request_ratio,
            today_estimated_cost_usd=today_estimated_cost_usd,
            daily_budget_limit_usd=round(daily_budget_limit_usd, 6),
            daily_budget_ratio=daily_budget_ratio,
            warning_level=warning_level,
        )

    async def get_billing_summary(
        self,
        user_id: int,
        *,
        hours: int = 72,
        limit: int = 100,
    ) -> UserSubscriptionBillingSummaryRead:
        user = await self.user_repo.get(id=user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        if hours < 1 or hours > 24 * 30:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="hours 必须在 1~720 之间")
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit 必须在 1~500 之间")

        since = datetime.utcnow() - timedelta(hours=hours)
        stmt = (
            select(LLMCallLog)
            .where(
                LLMCallLog.user_id == user_id,
                LLMCallLog.created_at >= since,
            )
            .order_by(LLMCallLog.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()

        items = [
            UserSubscriptionBillingItemRead(
                id=item.id,
                created_at=item.created_at,
                project_id=item.project_id,
                request_type=item.request_type,
                model=item.model,
                status=item.status,
                estimated_input_tokens=item.estimated_input_tokens or 0,
                estimated_output_tokens=item.estimated_output_tokens or 0,
                estimated_cost_usd=round(float(item.estimated_cost_usd or 0.0), 8),
                latency_ms=item.latency_ms,
            )
            for item in rows
        ]

        total_calls = int(
            await self.session.scalar(
                select(func.count(LLMCallLog.id)).where(
                    LLMCallLog.user_id == user_id,
                    LLMCallLog.created_at >= since,
                )
            )
            or 0
        )
        success_calls = int(
            await self.session.scalar(
                select(func.count(LLMCallLog.id)).where(
                    LLMCallLog.user_id == user_id,
                    LLMCallLog.created_at >= since,
                    LLMCallLog.status == "success",
                )
            )
            or 0
        )
        total_estimated_cost_usd = round(
            float(
                await self.session.scalar(
                    select(func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0)).where(
                        LLMCallLog.user_id == user_id,
                        LLMCallLog.created_at >= since,
                    )
                )
                or 0.0
            ),
            8,
        )

        return UserSubscriptionBillingSummaryRead(
            user_id=user_id,
            hours=hours,
            total_calls=total_calls,
            success_calls=success_calls,
            total_estimated_cost_usd=total_estimated_cost_usd,
            items=items,
        )

    async def apply_request_compensation(
        self,
        user_id: int,
        *,
        request_quota: int,
        note: str,
        actor_user_id: Optional[int] = None,
        actor_username: str = "system",
    ) -> UserSubscriptionCompensationRead:
        user = await self.user_repo.get(id=user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if request_quota < 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request_quota 必须大于 0")

        today = date.today()
        usage_stmt = select(UserDailyRequest).where(
            UserDailyRequest.user_id == user_id,
            UserDailyRequest.request_date == today,
        )
        usage_record = (await self.session.execute(usage_stmt)).scalars().first()
        if usage_record is None:
            usage_record = UserDailyRequest(user_id=user_id, request_date=today, request_count=0)
            self.session.add(usage_record)
            await self.session.flush()

        before_used = int(usage_record.request_count or 0)
        after_used = max(0, before_used - int(request_quota))
        usage_record.request_count = after_used

        subscription = await self.subscription_repo.get_by_user_id(user_id)
        old_snapshot = self._snapshot(subscription, user_id)
        old_snapshot["daily_request_used"] = before_used
        new_snapshot = self._snapshot(subscription, user_id)
        new_snapshot["daily_request_used"] = after_used
        new_snapshot["compensation"] = {
            "request_quota": int(request_quota),
            "note": note.strip(),
            "operator": actor_username,
            "at": datetime.utcnow().isoformat(),
        }

        created_at = datetime.utcnow()
        self.session.add(
            UserSubscriptionAuditLog(
                user_id=user_id,
                admin_user_id=actor_user_id,
                admin_username=actor_username,
                action="compensate_request_quota",
                old_snapshot=json.dumps(old_snapshot, ensure_ascii=False),
                new_snapshot=json.dumps(new_snapshot, ensure_ascii=False),
                created_at=created_at,
            )
        )
        await self.session.commit()

        return UserSubscriptionCompensationRead(
            user_id=user_id,
            request_quota=int(request_quota),
            before_daily_request_used=before_used,
            after_daily_request_used=after_used,
            note=note.strip(),
            operator=actor_username,
            created_at=created_at,
        )
