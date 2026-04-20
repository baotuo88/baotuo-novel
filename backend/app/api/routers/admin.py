# AIMETA P=管理员API_用户管理和系统配置|R=管理员CRUD_系统配置_统计|NR=不含普通用户功能|E=route:POST_GET_/api/admin/*|X=http|A=用户CRUD_配置_统计|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import asyncio
import logging
import csv
import io
import ipaddress
import math
import os
import socket
import smtplib
import time
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import settings
from ...core.dependencies import get_current_admin
from ...db.session import AsyncSessionLocal, get_session
from ...models import (
    Chapter,
    ChapterOutline,
    ChapterVersion,
    GenerationTask,
    LLMCallLog,
    NovelProject,
    SystemConfig,
    UsageMetric,
    User,
)
from ...schemas.admin import (
    AdminNovelSummary,
    DailyRequestLimit,
    LLMCallLogRead,
    LLMErrorTopItem,
    LLMGroupedTrendResponse,
    LLMGroupedTrendSeries,
    LLMCallSummary,
    LLMBudgetAlertItem,
    LLMBudgetAlertResponse,
    ConfigHealthItem,
    ConfigHealthResponse,
    WriterTaskAlertIssue,
    WriterTaskAlertChannelStatus,
    WriterTaskAlertSnapshot,
    WriterTaskAlertResponse,
    WriterTaskQueueItem,
    WriterTaskQueueSummary,
    WriterTaskFailureTopItem,
    WriterTaskQueueResponse,
    WriterTaskRetryRequest,
    WriterTaskRetryResponse,
    Statistics,
    UpdateLogCreate,
    UpdateLogRead,
    UpdateLogUpdate,
)
from ...schemas.config import SystemConfigCreate, SystemConfigRead, SystemConfigUpdate
from ...schemas.prompt import (
    PromptCreate,
    PromptRead,
    PromptUpdate,
    WritingPresetActivateRequest,
    WritingPresetRead,
    WritingPresetUpsert,
)
from ...schemas.novel import (
    Chapter as ChapterSchema,
    EvaluateChapterRequest,
    GenerateChapterRequest,
    NovelProject as NovelProjectSchema,
    NovelSectionResponse,
    NovelSectionType,
)
from ...schemas.user import (
    PasswordChangeRequest,
    User as UserSchema,
    UserSubscriptionAuditRead,
    UserSubscriptionCompensationRead,
    UserSubscriptionCompensationRequest,
    UserCreateAdmin,
    UserSubscriptionRead,
    UserSubscriptionUpsert,
    UserUpdateAdmin,
)
from ...services.auth_service import AuthService
from ...services.admin_setting_service import AdminSettingService
from ...services.config_service import ConfigService
from ...services.llm_config_service import LLMConfigService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.update_log_service import UpdateLogService
from ...services.user_service import UserService
from ...services.user_subscription_service import UserSubscriptionService
from ...services.generation_alert_service import GenerationAlertService
from ...services.generation_task_service import (
    TASK_STATUS_CANCELED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_TYPE_BLUEPRINT_GENERATION,
    TASK_TYPE_CHAPTER_GENERATION,
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

_WRITER_ACTIVE_STATUSES = {"generating", "evaluating", "waiting_for_confirm"}
_WRITER_FAILED_STATUSES = {"failed", "evaluation_failed"}
_WRITER_RETRY_INFLIGHT: set[int] = set()


def _parse_env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


_WRITER_TASK_HEARTBEAT_TIMEOUT_SECONDS = _parse_env_int(
    "GENERATION_TASK_STALE_TIMEOUT_SECONDS",
    default=300,
    min_value=30,
    max_value=3600,
)
_WRITER_TASK_RECENT_WINDOW_HOURS = _parse_env_int(
    "WRITER_TASK_METRIC_WINDOW_HOURS",
    default=24,
    min_value=1,
    max_value=24 * 7,
)


def get_prompt_service(session: AsyncSession = Depends(get_session)) -> PromptService:
    return PromptService(session)


def get_update_log_service(session: AsyncSession = Depends(get_session)) -> UpdateLogService:
    return UpdateLogService(session)


def get_admin_setting_service(session: AsyncSession = Depends(get_session)) -> AdminSettingService:
    return AdminSettingService(session)


def get_config_service(session: AsyncSession = Depends(get_session)) -> ConfigService:
    return ConfigService(session)


def get_novel_service(session: AsyncSession = Depends(get_session)) -> NovelService:
    return NovelService(session)


def get_user_service(session: AsyncSession = Depends(get_session)) -> UserService:
    return UserService(session)


def get_user_subscription_service(session: AsyncSession = Depends(get_session)) -> UserSubscriptionService:
    return UserSubscriptionService(session)


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(session)


def _build_llm_log_filters(
    *,
    hours: int,
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    project_id: Optional[str] = None,
):
    if hours < 1 or hours > 24 * 30:
        raise HTTPException(status_code=400, detail="hours 必须在 1~720 之间")

    since = datetime.utcnow() - timedelta(hours=hours)
    filters = [LLMCallLog.created_at >= since]
    if status_filter:
        filters.append(LLMCallLog.status == status_filter)
    if request_type:
        filters.append(LLMCallLog.request_type == request_type)
    if model:
        filters.append(LLMCallLog.model == model)
    if user_id is not None:
        filters.append(LLMCallLog.user_id == user_id)
    if project_id:
        filters.append(LLMCallLog.project_id == project_id)
    return filters


def _parse_positive_float(raw_value: Optional[str], default: float = 0.0) -> float:
    if raw_value in (None, ""):
        return default
    try:
        return max(0.0, float(str(raw_value).strip()))
    except Exception:
        return default


def _parse_bool(raw_value: Optional[str], default: bool = False) -> bool:
    if raw_value is None:
        return default
    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_clamped_int(raw_value: Optional[str], *, default: int, min_value: int, max_value: int) -> int:
    try:
        value = int(str(raw_value).strip()) if raw_value is not None else default
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


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


def _budget_level(usage_ratio: float, warning_threshold: float, critical_threshold: float) -> str:
    if usage_ratio >= 1:
        return "exceeded"
    if usage_ratio >= critical_threshold:
        return "critical"
    if usage_ratio >= warning_threshold:
        return "warning"
    return "ok"


def _is_non_public_ip(ip_value: str) -> Optional[bool]:
    try:
        ip = ipaddress.ip_address(ip_value)
    except ValueError:
        return None
    return not ip.is_global


def _validate_webhook_probe_target(raw_url: str, *, resolve_dns: bool) -> tuple[bool, str]:
    url = str(raw_url or "").strip()
    if not url:
        return False, "地址为空"

    try:
        parsed = urlsplit(url)
    except Exception:
        return False, "URL 解析失败"

    if parsed.scheme not in {"http", "https"}:
        return False, "仅允许 http/https 协议"

    if parsed.username or parsed.password:
        return False, "不允许携带用户名或密码"

    host = (parsed.hostname or "").strip()
    if not host:
        return False, "缺少主机名"
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return False, "禁止访问本机地址"
    if host.endswith(".local"):
        return False, "禁止访问内网主机域名"

    host_ip_check = _is_non_public_ip(host)
    if host_ip_check is True:
        return False, "禁止访问私网/保留地址"

    if resolve_dns:
        try:
            resolved = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except Exception:
            return False, "域名解析失败"

        for item in resolved:
            sockaddr = item[4]
            ip_value = str(sockaddr[0] if isinstance(sockaddr, tuple) else "")
            ip_check = _is_non_public_ip(ip_value)
            if ip_check is True:
                return False, "解析结果包含私网/保留地址"
    return True, "ok"


def _resolve_retry_action(retry_mode: str, current_status: str) -> Literal["generate", "evaluate"]:
    if retry_mode in {"generate", "evaluate"}:
        return retry_mode  # type: ignore[return-value]
    if current_status in {"evaluation_failed", "evaluating", "waiting_for_confirm"}:
        return "evaluate"
    return "generate"


async def _mark_retry_failed_state(
    session: AsyncSession,
    *,
    chapter_id: int,
    action: Literal["generate", "evaluate"],
    reason: str,
) -> None:
    chapter = await session.get(Chapter, chapter_id)
    if not chapter:
        return
    failure_status = "evaluation_failed" if action == "evaluate" else "failed"
    chapter.status = failure_status
    await session.commit()
    logger.warning(
        "管理员重试任务失败，已回写章节状态：chapter_id=%s status=%s reason=%s",
        chapter_id,
        failure_status,
        reason[:240],
    )


async def _run_writer_retry_task(
    *,
    chapter_id: int,
    action: Literal["generate", "evaluate"],
    writing_notes: Optional[str],
    trigger_admin_id: int,
) -> None:
    try:
        async with AsyncSessionLocal() as task_session:
            row = (
                await task_session.execute(
                    select(
                        Chapter.project_id,
                        Chapter.chapter_number,
                        NovelProject.user_id,
                    )
                    .join(NovelProject, Chapter.project_id == NovelProject.id)
                    .where(Chapter.id == chapter_id)
                )
            ).first()
            if not row:
                raise RuntimeError(f"章节不存在: {chapter_id}")

            project_id = str(row[0])
            chapter_number = int(row[1])
            owner_user_id = int(row[2])
            owner_user = await task_session.get(User, owner_user_id)
            if not owner_user:
                raise RuntimeError(f"项目归属用户不存在: {owner_user_id}")
            if not owner_user.is_active:
                raise RuntimeError(f"项目归属用户已禁用: {owner_user_id}")

            if action == "generate":
                from .writer import generate_chapter as writer_generate_chapter

                admin_request = Request(
                    scope={
                        "type": "http",
                        "method": "POST",
                        "path": f"/api/admin/writer-task-queue/retry/{chapter_id}",
                        "headers": [],
                    }
                )
                admin_request.state.request_id = f"admin-retry-{uuid4().hex[:12]}"
                await writer_generate_chapter(
                    project_id=project_id,
                    payload=GenerateChapterRequest(
                        chapter_number=chapter_number,
                        writing_notes=(writing_notes or None),
                    ),
                    request=admin_request,
                    session=task_session,
                    current_user=owner_user,
                )
            else:
                from .writer import evaluate_chapter as writer_evaluate_chapter

                await writer_evaluate_chapter(
                    project_id=project_id,
                    request=EvaluateChapterRequest(chapter_number=chapter_number),
                    session=task_session,
                    current_user=owner_user,
                )

            logger.info(
                "管理员重试任务执行完成：admin_id=%s chapter_id=%s action=%s",
                trigger_admin_id,
                chapter_id,
                action,
            )
    except Exception as exc:
        logger.exception(
            "管理员重试任务执行失败：admin_id=%s chapter_id=%s action=%s error=%s",
            trigger_admin_id,
            chapter_id,
            action,
            exc,
        )
        try:
            async with AsyncSessionLocal() as fallback_session:
                await _mark_retry_failed_state(
                    fallback_session,
                    chapter_id=chapter_id,
                    action=action,
                    reason=str(exc),
                )
        except Exception:
            logger.exception("管理员重试任务写回失败状态时异常：chapter_id=%s action=%s", chapter_id, action)
    finally:
        _WRITER_RETRY_INFLIGHT.discard(chapter_id)


@router.get("/stats", response_model=Statistics)
async def read_statistics(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> Statistics:
    novel_count = await session.scalar(select(func.count(NovelProject.id))) or 0
    user_count = await session.scalar(select(func.count(User.id))) or 0
    usage = await session.get(UsageMetric, "api_request_count")
    api_request_count = usage.value if usage else 0
    logger.info("管理员获取统计数据：小说=%s，用户=%s，请求=%s", novel_count, user_count, api_request_count)
    return Statistics(novel_count=novel_count, user_count=user_count, api_request_count=api_request_count)


@router.get("/llm-call-logs", response_model=List[LLMCallLogRead])
async def list_llm_call_logs(
    limit: int = 50,
    offset: int = 0,
    hours: int = 24,
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    project_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> List[LLMCallLogRead]:
    """按条件筛选 LLM 调用日志，默认返回近 24 小时最新 50 条。"""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit 必须在 1~200 之间")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset 不能为负数")

    filters = _build_llm_log_filters(
        hours=hours,
        status_filter=status_filter,
        request_type=request_type,
        model=model,
        user_id=user_id,
        project_id=project_id,
    )
    stmt = select(LLMCallLog).where(*filters)

    stmt = stmt.order_by(LLMCallLog.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    logs = result.scalars().all()
    logger.info(
        "管理员读取 LLM 调用日志：count=%s hours=%s status=%s request_type=%s model=%s user_id=%s project_id=%s",
        len(logs),
        hours,
        status_filter,
        request_type,
        model,
        user_id,
        project_id,
    )
    return [LLMCallLogRead.model_validate(item) for item in logs]


@router.get("/llm-call-logs/summary", response_model=LLMCallSummary)
async def get_llm_call_summary(
    hours: int = 24,
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    project_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> LLMCallSummary:
    """获取 LLM 调用聚合统计（成功率、时延、估算成本等）。"""
    filters = _build_llm_log_filters(
        hours=hours,
        status_filter=status_filter,
        request_type=request_type,
        model=model,
        user_id=user_id,
        project_id=project_id,
    )

    total_calls = await session.scalar(select(func.count(LLMCallLog.id)).where(*filters)) or 0
    success_calls = await session.scalar(
        select(func.count(LLMCallLog.id)).where(*filters, LLMCallLog.status == "success")
    ) or 0
    error_calls = await session.scalar(
        select(func.count(LLMCallLog.id)).where(*filters, LLMCallLog.status == "error")
    ) or 0

    avg_latency_ms_value = await session.scalar(
        select(func.avg(LLMCallLog.latency_ms)).where(*filters, LLMCallLog.latency_ms.is_not(None))
    )
    total_input_tokens = await session.scalar(
        select(func.coalesce(func.sum(LLMCallLog.estimated_input_tokens), 0)).where(*filters)
    ) or 0
    total_output_tokens = await session.scalar(
        select(func.coalesce(func.sum(LLMCallLog.estimated_output_tokens), 0)).where(*filters)
    ) or 0
    total_estimated_cost = await session.scalar(
        select(func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0)).where(*filters)
    ) or 0.0

    success_rate = round((success_calls / total_calls) * 100, 2) if total_calls else 0.0
    avg_latency_ms = round(float(avg_latency_ms_value or 0.0), 2)

    logger.info(
        "管理员读取 LLM 聚合统计：hours=%s total=%s success=%s error=%s cost=%.6f",
        hours,
        total_calls,
        success_calls,
        error_calls,
        total_estimated_cost,
    )
    return LLMCallSummary(
        period_hours=hours,
        total_calls=total_calls,
        success_calls=success_calls,
        error_calls=error_calls,
        success_rate=success_rate,
        avg_latency_ms=avg_latency_ms,
        total_input_tokens=int(total_input_tokens),
        total_output_tokens=int(total_output_tokens),
        total_estimated_cost_usd=round(float(total_estimated_cost), 6),
    )


@router.get("/llm-call-logs/hourly-grouped", response_model=LLMGroupedTrendResponse)
async def get_llm_hourly_grouped_trend(
    hours: int = 24,
    group_by: Literal["model", "user"] = "model",
    limit: int = 5,
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    project_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> LLMGroupedTrendResponse:
    """按小时聚合，并按模型/用户分组输出 TopN 趋势序列。"""
    if limit < 1 or limit > 20:
        raise HTTPException(status_code=400, detail="limit 必须在 1~20 之间")

    filters = _build_llm_log_filters(
        hours=hours,
        status_filter=status_filter,
        request_type=request_type,
        model=model,
        user_id=user_id,
        project_id=project_id,
    )

    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(hours=hours - 1)
    bucket_datetimes = [start + timedelta(hours=i) for i in range(hours)]
    buckets = [dt.strftime("%m-%d %H:00") for dt in bucket_datetimes]
    bucket_index = {label: idx for idx, label in enumerate(buckets)}

    stmt = select(LLMCallLog).where(*filters).order_by(LLMCallLog.created_at.asc())
    result = await session.execute(stmt)
    logs = result.scalars().all()

    group_points: dict[str, list[int]] = {}
    group_totals: dict[str, int] = {}

    for log in logs:
        if group_by == "model":
            key = (log.model or "unknown-model").strip() or "unknown-model"
        else:
            key = f"user:{log.user_id}" if log.user_id is not None else "anonymous"

        if key not in group_points:
            group_points[key] = [0] * len(buckets)
            group_totals[key] = 0

        created_at = log.created_at or now
        if getattr(created_at, "tzinfo", None) is not None:
            created_at = created_at.replace(tzinfo=None)
        label = created_at.replace(minute=0, second=0, microsecond=0).strftime("%m-%d %H:00")
        idx = bucket_index.get(label)
        if idx is None:
            continue

        group_points[key][idx] += 1
        group_totals[key] += 1

    sorted_keys = sorted(group_totals.keys(), key=lambda item: (group_totals[item], item), reverse=True)
    top_keys = sorted_keys[:limit]
    series = [
        LLMGroupedTrendSeries(
            key=key,
            total_calls=group_totals[key],
            points=group_points[key],
        )
        for key in top_keys
    ]

    logger.info(
        "管理员读取 LLM 小时趋势：group_by=%s hours=%s groups=%s logs=%s",
        group_by,
        hours,
        len(series),
        len(logs),
    )
    return LLMGroupedTrendResponse(
        period_hours=hours,
        group_by=group_by,
        buckets=buckets,
        series=series,
    )


@router.get("/llm-call-logs/errors-top", response_model=List[LLMErrorTopItem])
async def get_llm_error_top(
    hours: int = 24,
    limit: int = 10,
    request_type: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    project_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> List[LLMErrorTopItem]:
    """返回高频错误 TopN，按错误类型+消息片段聚合。"""
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="limit 必须在 1~50 之间")

    filters = _build_llm_log_filters(
        hours=hours,
        request_type=request_type,
        model=model,
        user_id=user_id,
        project_id=project_id,
    )
    filters.append(LLMCallLog.status == "error")

    stmt = select(LLMCallLog).where(*filters).order_by(LLMCallLog.created_at.desc()).limit(5000)
    result = await session.execute(stmt)
    logs = result.scalars().all()

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for log in logs:
        error_type = (log.error_type or "UnknownError").strip() or "UnknownError"
        sample_message = (log.error_message or "未知错误").strip() or "未知错误"
        if len(sample_message) > 180:
            sample_message = f"{sample_message[:180]}..."
        key = (error_type, sample_message)

        current = grouped.get(key)
        if not current:
            grouped[key] = {
                "error_type": error_type,
                "sample_message": sample_message,
                "count": 1,
                "latest_at": log.created_at or datetime.utcnow(),
            }
            continue

        current["count"] = int(current["count"]) + 1
        current_latest = current["latest_at"]
        if isinstance(current_latest, datetime) and log.created_at and log.created_at > current_latest:
            current["latest_at"] = log.created_at

    sorted_items = sorted(
        grouped.values(),
        key=lambda item: (
            int(item["count"]),
            item["latest_at"] if isinstance(item["latest_at"], datetime) else datetime.min,
        ),
        reverse=True,
    )

    top_items = [
        LLMErrorTopItem(
            error_type=str(item["error_type"]),
            sample_message=str(item["sample_message"]),
            count=int(item["count"]),
            latest_at=item["latest_at"] if isinstance(item["latest_at"], datetime) else datetime.utcnow(),
        )
        for item in sorted_items[:limit]
    ]

    logger.info("管理员读取 LLM 错误 TopN：hours=%s limit=%s results=%s", hours, limit, len(top_items))
    return top_items


@router.get("/llm-call-logs/export.csv")
async def export_llm_call_logs_csv(
    hours: int = 24,
    status_filter: Optional[str] = None,
    request_type: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    project_id: Optional[str] = None,
    max_rows: int = 5000,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
):
    """导出调用日志 CSV，默认导出近 24 小时最多 5000 条。"""
    if max_rows < 1 or max_rows > 50000:
        raise HTTPException(status_code=400, detail="max_rows 必须在 1~50000 之间")

    filters = _build_llm_log_filters(
        hours=hours,
        status_filter=status_filter,
        request_type=request_type,
        model=model,
        user_id=user_id,
        project_id=project_id,
    )
    stmt = select(LLMCallLog).where(*filters).order_by(LLMCallLog.created_at.desc()).limit(max_rows)
    result = await session.execute(stmt)
    logs = result.scalars().all()

    csv_buffer = io.StringIO()
    csv_buffer.write("\ufeff")
    writer = csv.writer(csv_buffer)
    writer.writerow(
        [
            "id",
            "created_at",
            "user_id",
            "project_id",
            "request_type",
            "provider",
            "model",
            "status",
            "latency_ms",
            "input_chars",
            "output_chars",
            "estimated_input_tokens",
            "estimated_output_tokens",
            "estimated_cost_usd",
            "finish_reason",
            "error_type",
            "error_message",
        ]
    )

    for log in logs:
        writer.writerow(
            [
                log.id,
                log.created_at.isoformat() if log.created_at else "",
                log.user_id if log.user_id is not None else "",
                log.project_id or "",
                log.request_type,
                log.provider,
                log.model or "",
                log.status,
                log.latency_ms if log.latency_ms is not None else "",
                log.input_chars,
                log.output_chars,
                log.estimated_input_tokens,
                log.estimated_output_tokens,
                log.estimated_cost_usd if log.estimated_cost_usd is not None else "",
                log.finish_reason or "",
                log.error_type or "",
                (log.error_message or "").replace("\n", " ").replace("\r", " "),
            ]
        )

    filename = f"llm_call_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    logger.info("管理员导出 LLM 调用日志：rows=%s filename=%s", len(logs), filename)

    response = StreamingResponse(
        iter([csv_buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@router.get("/llm-budget-alerts", response_model=LLMBudgetAlertResponse)
async def get_llm_budget_alerts(
    limit_each: int = 20,
    only_alerting: bool = True,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> LLMBudgetAlertResponse:
    """返回今日预算使用告警（全局 / 用户 / 项目）。"""
    if limit_each < 1 or limit_each > 100:
        raise HTTPException(status_code=400, detail="limit_each 必须在 1~100 之间")

    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    budget_key_stmt = select(SystemConfig).where(
        (SystemConfig.key == "llm.budget.daily_usd.global")
        | (SystemConfig.key == "llm.budget.daily_usd.user.default")
        | (SystemConfig.key == "llm.budget.daily_usd.project.default")
        | (SystemConfig.key == "llm.budget.alert.thresholds")
        | (SystemConfig.key.like("llm.budget.daily_usd.user.%"))
        | (SystemConfig.key.like("llm.budget.daily_usd.project.%"))
    )
    config_result = await session.execute(budget_key_stmt)
    configs = config_result.scalars().all()
    config_map = {item.key: item.value for item in configs}

    warning_threshold, critical_threshold = _parse_thresholds(config_map.get("llm.budget.alert.thresholds"))

    global_limit = _parse_positive_float(config_map.get("llm.budget.daily_usd.global"), default=0.0)
    user_default_limit = _parse_positive_float(config_map.get("llm.budget.daily_usd.user.default"), default=0.0)
    project_default_limit = _parse_positive_float(config_map.get("llm.budget.daily_usd.project.default"), default=0.0)

    user_overrides: dict[int, float] = {}
    project_overrides: dict[str, float] = {}
    user_prefix = "llm.budget.daily_usd.user."
    project_prefix = "llm.budget.daily_usd.project."
    for key, value in config_map.items():
        if key.startswith(user_prefix) and key != "llm.budget.daily_usd.user.default":
            suffix = key[len(user_prefix):].strip()
            if suffix.isdigit():
                user_overrides[int(suffix)] = _parse_positive_float(value, default=0.0)
        if key.startswith(project_prefix) and key != "llm.budget.daily_usd.project.default":
            suffix = key[len(project_prefix):].strip()
            if suffix:
                project_overrides[suffix] = _parse_positive_float(value, default=0.0)

    global_spent = float(
        await session.scalar(
            select(func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0)).where(
                LLMCallLog.created_at >= day_start,
                LLMCallLog.status == "success",
            )
        ) or 0.0
    )

    global_alert: Optional[LLMBudgetAlertItem] = None
    if global_limit > 0:
        ratio = global_spent / global_limit if global_limit > 0 else 0.0
        level = _budget_level(ratio, warning_threshold, critical_threshold)
        item = LLMBudgetAlertItem(
            scope_type="global",
            scope_key="global",
            scope_label="全局预算",
            spent_usd=round(global_spent, 6),
            limit_usd=round(global_limit, 6),
            usage_ratio=round(ratio, 6),
            level=level,
            is_alerting=level != "ok",
        )
        if not only_alerting or item.is_alerting:
            global_alert = item

    user_spend_stmt = (
        select(
            LLMCallLog.user_id,
            func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0).label("spent"),
        )
        .where(
            LLMCallLog.created_at >= day_start,
            LLMCallLog.status == "success",
            LLMCallLog.user_id.is_not(None),
        )
        .group_by(LLMCallLog.user_id)
    )
    user_spend_rows = (await session.execute(user_spend_stmt)).all()
    user_spent_map = {int(row[0]): float(row[1] or 0.0) for row in user_spend_rows if row[0] is not None}
    user_candidates = sorted(set(user_spent_map.keys()) | set(user_overrides.keys()))

    user_name_map: dict[int, str] = {}
    if user_candidates:
        user_rows = (
            await session.execute(select(User.id, User.username).where(User.id.in_(user_candidates)))
        ).all()
        user_name_map = {int(row[0]): str(row[1]) for row in user_rows}

    user_alerts: list[LLMBudgetAlertItem] = []
    for user_id in user_candidates:
        limit = user_overrides.get(user_id, user_default_limit)
        if limit <= 0:
            continue
        spent = user_spent_map.get(user_id, 0.0)
        ratio = spent / limit if limit > 0 else 0.0
        level = _budget_level(ratio, warning_threshold, critical_threshold)
        item = LLMBudgetAlertItem(
            scope_type="user",
            scope_key=str(user_id),
            scope_label=user_name_map.get(user_id, f"用户 {user_id}"),
            spent_usd=round(spent, 6),
            limit_usd=round(limit, 6),
            usage_ratio=round(ratio, 6),
            level=level,
            is_alerting=level != "ok",
        )
        if only_alerting and not item.is_alerting:
            continue
        user_alerts.append(item)

    user_alerts = sorted(
        user_alerts,
        key=lambda item: (item.is_alerting, item.usage_ratio, item.spent_usd),
        reverse=True,
    )[:limit_each]

    project_spend_stmt = (
        select(
            LLMCallLog.project_id,
            func.coalesce(func.sum(LLMCallLog.estimated_cost_usd), 0.0).label("spent"),
        )
        .where(
            LLMCallLog.created_at >= day_start,
            LLMCallLog.status == "success",
            LLMCallLog.project_id.is_not(None),
            LLMCallLog.project_id != "",
        )
        .group_by(LLMCallLog.project_id)
    )
    project_spend_rows = (await session.execute(project_spend_stmt)).all()
    project_spent_map = {
        str(row[0]): float(row[1] or 0.0)
        for row in project_spend_rows
        if row[0] not in (None, "")
    }
    project_candidates = sorted(set(project_spent_map.keys()) | set(project_overrides.keys()))

    project_info_map: dict[str, tuple[str, int]] = {}
    owner_id_set: set[int] = set()
    if project_candidates:
        project_rows = (
            await session.execute(
                select(NovelProject.id, NovelProject.title, NovelProject.user_id).where(
                    NovelProject.id.in_(project_candidates)
                )
            )
        ).all()
        for project_id, title, owner_id in project_rows:
            pid = str(project_id)
            project_info_map[pid] = (str(title or pid), int(owner_id))
            owner_id_set.add(int(owner_id))

    owner_name_map: dict[int, str] = {}
    if owner_id_set:
        owner_rows = (await session.execute(select(User.id, User.username).where(User.id.in_(owner_id_set)))).all()
        owner_name_map = {int(row[0]): str(row[1]) for row in owner_rows}

    project_alerts: list[LLMBudgetAlertItem] = []
    for project_id in project_candidates:
        limit = project_overrides.get(project_id, project_default_limit)
        if limit <= 0:
            continue
        spent = project_spent_map.get(project_id, 0.0)
        ratio = spent / limit if limit > 0 else 0.0
        level = _budget_level(ratio, warning_threshold, critical_threshold)
        title, owner_id = project_info_map.get(project_id, (project_id, 0))
        owner_label = owner_name_map.get(owner_id, "")
        scope_label = f"{title}" if not owner_label else f"{title}（{owner_label}）"
        item = LLMBudgetAlertItem(
            scope_type="project",
            scope_key=project_id,
            scope_label=scope_label,
            spent_usd=round(spent, 6),
            limit_usd=round(limit, 6),
            usage_ratio=round(ratio, 6),
            level=level,
            is_alerting=level != "ok",
        )
        if only_alerting and not item.is_alerting:
            continue
        project_alerts.append(item)

    project_alerts = sorted(
        project_alerts,
        key=lambda item: (item.is_alerting, item.usage_ratio, item.spent_usd),
        reverse=True,
    )[:limit_each]

    logger.info(
        "管理员读取预算预警：global=%s users=%s projects=%s only_alerting=%s",
        "yes" if global_alert else "no",
        len(user_alerts),
        len(project_alerts),
        only_alerting,
    )
    return LLMBudgetAlertResponse(
        generated_at=datetime.utcnow(),
        warning_threshold=warning_threshold,
        critical_threshold=critical_threshold,
        global_alert=global_alert,
        users=user_alerts,
        projects=project_alerts,
    )


@router.get("/config-health", response_model=ConfigHealthResponse)
async def get_config_health(
    run_connectivity: bool = True,
    webhook_url: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> ConfigHealthResponse:
    keys = [
        "llm.api_key",
        "llm.base_url",
        "llm.model",
        "smtp.server",
        "smtp.port",
        "smtp.username",
        "smtp.password",
        "smtp.from",
        "auth.allow_registration",
        "auth.linuxdo_enabled",
        "linuxdo.client_id",
        "linuxdo.client_secret",
        "linuxdo.redirect_uri",
        "linuxdo.auth_url",
        "linuxdo.token_url",
        "linuxdo.user_info_url",
        "generation.task.worker_count",
        "generation.submit.max_running_per_user",
        "generation.submit.max_running_per_project",
        "generation.submit.max_queued_per_user",
        "generation.submit.max_queued_per_project",
        "generation.submit.max_running_blueprint_per_user",
        "generation.submit.max_running_chapter_per_project",
        "generation.alert.webhook_url",
        "generation.alert.email_to",
        "generation.alert.enabled",
    ]
    config_rows = (
        await session.execute(
            select(SystemConfig.key, SystemConfig.value).where(SystemConfig.key.in_(keys))
        )
    ).all()
    config_map = {str(key): str(value or "") for key, value in config_rows}

    items: list[ConfigHealthItem] = []

    def _append_item(
        *,
        key: str,
        label: str,
        level: Literal["pass", "warn", "fail"],
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        items.append(
            ConfigHealthItem(
                key=key,
                label=label,
                level=level,
                message=message,
                details=details or {},
                checked_at=datetime.utcnow(),
            )
        )

    secret_key_len = len(str(settings.secret_key or "").strip())
    admin_password_default = settings.admin_default_password == "ChangeMe123!"
    security_level: Literal["pass", "warn", "fail"] = "pass"
    security_messages: list[str] = []
    if secret_key_len < 24:
        security_level = "fail"
        security_messages.append("SECRET_KEY 长度不足（建议至少 24 位）")
    if admin_password_default:
        security_level = "warn" if security_level == "pass" else security_level
        security_messages.append("默认管理员密码仍为初始值")
    if not security_messages:
        security_messages.append("安全基础配置正常")
    _append_item(
        key="security.baseline",
        label="安全基线",
        level=security_level,
        message="；".join(security_messages),
        details={
            "secret_key_length": secret_key_len,
            "admin_default_password_unchanged": admin_password_default,
        },
    )

    llm_api_key = str(config_map.get("llm.api_key") or settings.openai_api_key or "").strip()
    llm_base_url = str(config_map.get("llm.base_url") or (settings.openai_base_url or "")).strip() or None
    llm_model = str(config_map.get("llm.model") or settings.openai_model_name or "").strip() or None
    if not llm_api_key:
        _append_item(
            key="llm.connectivity",
            label="LLM 连通性",
            level="fail",
            message="未配置 llm.api_key，系统模型调用不可用",
            details={"model": llm_model, "base_url": llm_base_url},
        )
    elif not run_connectivity:
        _append_item(
            key="llm.connectivity",
            label="LLM 连通性",
            level="pass",
            message="LLM 配置已存在（未执行在线连通测试）",
            details={"model": llm_model, "base_url": llm_base_url},
        )
    else:
        llm_probe = await LLMConfigService(session).test_connection(
            api_key=llm_api_key,
            base_url=llm_base_url,
            model=llm_model,
        )
        _append_item(
            key="llm.connectivity",
            label="LLM 连通性",
            level="pass" if bool(llm_probe.get("success")) else "fail",
            message=str(llm_probe.get("message") or "LLM 连通性检测完成"),
            details={
                "provider": llm_probe.get("provider"),
                "latency_ms": llm_probe.get("latency_ms"),
                "model_count": llm_probe.get("model_count"),
                "sample_models": llm_probe.get("sample_models"),
            },
        )

    smtp_required_keys = ["smtp.server", "smtp.port", "smtp.username", "smtp.password", "smtp.from"]
    smtp_values = {key: str(config_map.get(key) or "").strip() for key in smtp_required_keys}
    missing_smtp_keys = [key for key, value in smtp_values.items() if not value]
    allow_registration = _parse_bool(config_map.get("auth.allow_registration"), settings.allow_registration)
    smtp_probe_ok = False
    smtp_probe_detail = ""
    if missing_smtp_keys:
        smtp_level: Literal["pass", "warn", "fail"] = "fail" if allow_registration else "warn"
        _append_item(
            key="smtp.connectivity",
            label="SMTP 连通性",
            level=smtp_level,
            message=(
                "SMTP 配置缺失，无法发送邮件验证码"
                if allow_registration
                else "SMTP 配置缺失（当前未开启注册可接受）"
            ),
            details={"missing_keys": missing_smtp_keys},
        )
    elif not run_connectivity:
        smtp_probe_ok = True
        _append_item(
            key="smtp.connectivity",
            label="SMTP 连通性",
            level="pass",
            message="SMTP 配置完整（未执行在线连通测试）",
            details={"server": smtp_values["smtp.server"], "port": smtp_values["smtp.port"]},
        )
    else:
        started = time.perf_counter()

        def _probe_smtp() -> None:
            smtp: Optional[smtplib.SMTP] = None
            try:
                server = smtp_values["smtp.server"]
                port = _parse_clamped_int(smtp_values["smtp.port"], default=465, min_value=1, max_value=65535)
                username = smtp_values["smtp.username"]
                password = smtp_values["smtp.password"]
                if port == 465:
                    smtp = smtplib.SMTP_SSL(server, port, timeout=10)
                else:
                    smtp = smtplib.SMTP(server, port, timeout=10)
                    smtp.starttls()
                if username and password:
                    smtp.login(username, password)
            finally:
                if smtp is not None:
                    try:
                        smtp.quit()
                    except Exception:
                        pass

        try:
            await asyncio.to_thread(_probe_smtp)
            smtp_probe_ok = True
            smtp_latency_ms = int((time.perf_counter() - started) * 1000)
            smtp_probe_detail = f"SMTP 连通测试成功（{smtp_latency_ms}ms）"
            _append_item(
                key="smtp.connectivity",
                label="SMTP 连通性",
                level="pass",
                message=smtp_probe_detail,
                details={
                    "server": smtp_values["smtp.server"],
                    "port": smtp_values["smtp.port"],
                    "latency_ms": smtp_latency_ms,
                },
            )
        except Exception as exc:  # noqa: BLE001
            smtp_probe_detail = str(exc)
            _append_item(
                key="smtp.connectivity",
                label="SMTP 连通性",
                level="fail" if allow_registration else "warn",
                message=f"SMTP 连通测试失败：{str(exc)[:180]}",
                details={"server": smtp_values["smtp.server"], "port": smtp_values["smtp.port"]},
            )

    webhook_target = str(webhook_url or "").strip() or str(config_map.get("generation.alert.webhook_url") or "").strip()
    if not webhook_target:
        _append_item(
            key="webhook.connectivity",
            label="Webhook 连通性",
            level="warn",
            message="未配置 generation.alert.webhook_url",
            details={},
        )
    else:
        webhook_safe, webhook_check_message = await asyncio.to_thread(
            _validate_webhook_probe_target,
            webhook_target,
            resolve_dns=run_connectivity,
        )
        if not webhook_safe:
            _append_item(
                key="webhook.connectivity",
                label="Webhook 连通性",
                level="fail",
                message=f"Webhook 地址安全校验失败：{webhook_check_message}",
                details={"url": webhook_target},
            )
            webhook_target = ""
    if webhook_target and not run_connectivity:
        _append_item(
            key="webhook.connectivity",
            label="Webhook 连通性",
            level="pass",
            message="Webhook 地址已配置（未执行在线连通测试）",
            details={"url": webhook_target},
        )
    elif webhook_target:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(
                    webhook_target,
                    json={
                        "event": "admin.config_health.probe",
                        "checked_at": datetime.utcnow().isoformat(),
                    },
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            latency_ms = int((time.perf_counter() - started) * 1000)
            _append_item(
                key="webhook.connectivity",
                label="Webhook 连通性",
                level="pass",
                message=f"Webhook 连通测试成功（{latency_ms}ms）",
                details={"url": webhook_target, "latency_ms": latency_ms},
            )
        except Exception as exc:  # noqa: BLE001
            _append_item(
                key="webhook.connectivity",
                label="Webhook 连通性",
                level="fail",
                message=f"Webhook 连通测试失败：{str(exc)[:180]}",
                details={"url": webhook_target},
            )

    linuxdo_enabled = _parse_bool(config_map.get("auth.linuxdo_enabled"), settings.enable_linuxdo_login)
    if linuxdo_enabled:
        linuxdo_required = [
            ("linuxdo.client_id", settings.linuxdo_client_id),
            ("linuxdo.client_secret", settings.linuxdo_client_secret),
            ("linuxdo.redirect_uri", settings.linuxdo_redirect_uri),
            ("linuxdo.auth_url", settings.linuxdo_auth_url),
            ("linuxdo.token_url", settings.linuxdo_token_url),
            ("linuxdo.user_info_url", settings.linuxdo_user_info_url),
        ]
        missing_linuxdo = [
            key
            for key, fallback in linuxdo_required
            if not str(config_map.get(key) or fallback or "").strip()
        ]
    else:
        missing_linuxdo = []

    if allow_registration and not smtp_probe_ok:
        registration_level: Literal["pass", "warn", "fail"] = "fail"
        registration_message = "注册已开启，但邮件链路不可用"
    elif linuxdo_enabled and missing_linuxdo:
        registration_level = "fail"
        registration_message = "Linux.do 登录已开启，但 OAuth 配置不完整"
    elif allow_registration or linuxdo_enabled:
        registration_level = "pass"
        registration_message = "注册链路配置可用"
    else:
        registration_level = "warn"
        registration_message = "注册与第三方登录均未开启"
    _append_item(
        key="registration.flow",
        label="注册链路",
        level=registration_level,
        message=registration_message,
        details={
            "allow_registration": allow_registration,
            "linuxdo_enabled": linuxdo_enabled,
            "missing_linuxdo_keys": missing_linuxdo,
            "smtp_probe": smtp_probe_detail,
        },
    )

    worker_count = _parse_clamped_int(
        config_map.get("generation.task.worker_count"),
        default=settings.generation_task_workers,
        min_value=1,
        max_value=32,
    )
    policy_values = {
        "max_running_per_user": _parse_clamped_int(
            config_map.get("generation.submit.max_running_per_user"),
            default=2,
            min_value=0,
            max_value=200,
        ),
        "max_running_per_project": _parse_clamped_int(
            config_map.get("generation.submit.max_running_per_project"),
            default=2,
            min_value=0,
            max_value=200,
        ),
        "max_queued_per_user": _parse_clamped_int(
            config_map.get("generation.submit.max_queued_per_user"),
            default=30,
            min_value=0,
            max_value=2000,
        ),
        "max_queued_per_project": _parse_clamped_int(
            config_map.get("generation.submit.max_queued_per_project"),
            default=20,
            min_value=0,
            max_value=2000,
        ),
        "max_running_blueprint_per_user": _parse_clamped_int(
            config_map.get("generation.submit.max_running_blueprint_per_user"),
            default=1,
            min_value=0,
            max_value=20,
        ),
        "max_running_chapter_per_project": _parse_clamped_int(
            config_map.get("generation.submit.max_running_chapter_per_project"),
            default=1,
            min_value=0,
            max_value=20,
        ),
    }
    policy_warnings: list[str] = []
    if worker_count < 1:
        policy_warnings.append("generation.task.worker_count 非法")
    if policy_values["max_running_per_user"] <= 0 and policy_values["max_queued_per_user"] <= 0:
        policy_warnings.append("用户维度运行与排队上限均关闭，存在打满风险")
    if policy_values["max_running_per_project"] <= 0 and policy_values["max_queued_per_project"] <= 0:
        policy_warnings.append("项目维度运行与排队上限均关闭，存在积压风险")
    _append_item(
        key="generation.policy",
        label="任务并发与限流策略",
        level="warn" if policy_warnings else "pass",
        message="；".join(policy_warnings) if policy_warnings else "任务并发与排队策略配置正常",
        details={
            "worker_count": worker_count,
            **policy_values,
        },
    )

    pass_count = sum(1 for item in items if item.level == "pass")
    warn_count = sum(1 for item in items if item.level == "warn")
    fail_count = sum(1 for item in items if item.level == "fail")
    overall_level: Literal["pass", "warn", "fail"]
    if fail_count > 0:
        overall_level = "fail"
    elif warn_count > 0:
        overall_level = "warn"
    else:
        overall_level = "pass"

    return ConfigHealthResponse(
        generated_at=datetime.utcnow(),
        overall_level=overall_level,
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        items=items,
    )


@router.get("/writer-task-alerts", response_model=WriterTaskAlertResponse)
async def get_writer_task_alerts(
    window_hours: int = 24,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> WriterTaskAlertResponse:
    if window_hours < 1 or window_hours > 24 * 7:
        raise HTTPException(status_code=400, detail="window_hours 必须在 1~168 之间")

    task_types = [TASK_TYPE_CHAPTER_GENERATION, TASK_TYPE_BLUEPRINT_GENERATION]
    failed_statuses = {TASK_STATUS_FAILED, TASK_STATUS_CANCELED}
    now_utc = datetime.now(timezone.utc)
    window_since = now_utc - timedelta(hours=window_hours)
    base_filters = [GenerationTask.task_type.in_(task_types)]

    status_rows = (
        await session.execute(
            select(GenerationTask.status, func.count(GenerationTask.id))
            .where(*base_filters)
            .group_by(GenerationTask.status)
        )
    ).all()
    status_counts = {str(status or "unknown"): int(count or 0) for status, count in status_rows}
    queued_count = int(status_counts.get(TASK_STATUS_QUEUED, 0))
    running_count = int(status_counts.get(TASK_STATUS_RUNNING, 0))

    stale_timeout_raw = await session.scalar(
        select(SystemConfig.value).where(SystemConfig.key == "generation.task.stale_timeout_seconds")
    )
    stale_timeout_seconds = _parse_clamped_int(
        str(stale_timeout_raw or ""),
        default=settings.generation_task_stale_timeout_seconds,
        min_value=30,
        max_value=24 * 3600,
    )

    running_rows = (
        await session.execute(
            select(
                GenerationTask.heartbeat_at,
                GenerationTask.updated_at,
                GenerationTask.started_at,
                GenerationTask.created_at,
            ).where(*base_filters, GenerationTask.status == TASK_STATUS_RUNNING)
        )
    ).all()
    stale_running_count = 0
    for heartbeat_at, updated_at, started_at, created_at in running_rows:
        heartbeat_anchor = heartbeat_at or updated_at or started_at or created_at
        if heartbeat_anchor is None:
            continue
        anchor = heartbeat_anchor if getattr(heartbeat_anchor, "tzinfo", None) is not None else heartbeat_anchor.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((now_utc - anchor).total_seconds()))
        if age_seconds >= stale_timeout_seconds:
            stale_running_count += 1

    recent_rows = (
        await session.execute(
            select(
                GenerationTask.status,
                GenerationTask.error_message,
                GenerationTask.status_message,
            ).where(
                *base_filters,
                GenerationTask.finished_at.is_not(None),
                GenerationTask.finished_at >= window_since,
            )
        )
    ).all()
    finished_recent_count = len(recent_rows)
    failed_recent_count = sum(1 for status, _, _ in recent_rows if str(status or "") in failed_statuses)
    failure_rate_percent = (
        round((failed_recent_count * 100.0) / finished_recent_count, 2)
        if finished_recent_count > 0
        else 0.0
    )
    timeout_recent_count = 0
    for _, error_message, status_message in recent_rows:
        merged = f"{error_message or ''} {status_message or ''}".lower()
        if "超时" in merged or "timeout" in merged:
            timeout_recent_count += 1

    failure_rows = (
        await session.execute(
            select(
                GenerationTask.error_message,
                GenerationTask.status_message,
            )
            .where(
                *base_filters,
                GenerationTask.status.in_(failed_statuses),
                GenerationTask.updated_at >= window_since,
            )
            .order_by(GenerationTask.updated_at.desc())
            .limit(500)
        )
    ).all()
    failure_counter: dict[str, tuple[str, int]] = {}
    for error_message, status_message in failure_rows:
        message = str(error_message or status_message or "任务失败").strip()
        key = message.splitlines()[0][:140] or "任务失败"
        sample = message[:260] or key
        previous = failure_counter.get(key)
        if not previous:
            failure_counter[key] = (sample, 1)
        else:
            failure_counter[key] = (previous[0], previous[1] + 1)
    failure_top = sorted(failure_counter.items(), key=lambda item: item[1][1], reverse=True)[:8]
    failure_top_items = [
        WriterTaskFailureTopItem(error_key=key, sample_message=meta[0], count=meta[1]) for key, meta in failure_top
    ]

    alert_service = GenerationAlertService(session)
    alert_policy = await alert_service.load_policy()
    smtp_config = await alert_service._load_smtp_config()

    channels = [
        WriterTaskAlertChannelStatus(
            channel="webhook",
            enabled=bool(alert_policy.enabled and alert_policy.webhook_url.strip()),
            configured=bool(alert_policy.webhook_url.strip()),
            target=alert_policy.webhook_url.strip() or None,
        ),
        WriterTaskAlertChannelStatus(
            channel="email",
            enabled=bool(alert_policy.enabled and alert_policy.email_to.strip() and smtp_config),
            configured=bool(alert_policy.email_to.strip() and smtp_config),
            target=alert_policy.email_to.strip() or None,
        ),
    ]

    issues: list[WriterTaskAlertIssue] = []
    if not alert_policy.enabled:
        issues.append(
            WriterTaskAlertIssue(
                key="alert_disabled",
                label="告警开关",
                level="warning",
                message="任务告警已关闭（generation.alert.enabled=false）",
                suggestion="建议在生产环境开启失败告警。",
            )
        )
    if (
        alert_policy.failure_rate_threshold_percent > 0
        and failure_rate_percent >= alert_policy.failure_rate_threshold_percent
    ):
        issues.append(
            WriterTaskAlertIssue(
                key="failure_rate_high",
                label="失败率过高",
                level="critical",
                message="最近窗口任务失败率超过阈值",
                value=failure_rate_percent,
                threshold=alert_policy.failure_rate_threshold_percent,
                suggestion="检查模型可用性、提示词与外部依赖稳定性。",
            )
        )
    if alert_policy.stale_running_threshold > 0 and stale_running_count >= alert_policy.stale_running_threshold:
        issues.append(
            WriterTaskAlertIssue(
                key="stale_running",
                label="卡住任务",
                level="critical",
                message="运行中卡住任务数量超过阈值",
                value=float(stale_running_count),
                threshold=float(alert_policy.stale_running_threshold),
                suggestion="关注 worker 健康状态和上游接口超时。",
            )
        )
    if alert_policy.queue_backlog_threshold > 0 and queued_count >= alert_policy.queue_backlog_threshold:
        issues.append(
            WriterTaskAlertIssue(
                key="queue_backlog",
                label="队列积压",
                level="warning",
                message="排队任务数量超过阈值",
                value=float(queued_count),
                threshold=float(alert_policy.queue_backlog_threshold),
                suggestion="提高 worker 并发或收紧提交限流策略。",
            )
        )
    if timeout_recent_count > 0:
        issues.append(
            WriterTaskAlertIssue(
                key="timeout_recent",
                label="超时任务",
                level="warning",
                message="最近窗口检测到任务执行超时",
                value=float(timeout_recent_count),
                threshold=0.0,
                suggestion="检查超时时间配置与模型响应时延。",
            )
        )
    if not issues:
        issues.append(
            WriterTaskAlertIssue(
                key="healthy",
                label="健康状态",
                level="info",
                message="当前未触发任务告警阈值",
            )
        )

    return WriterTaskAlertResponse(
        generated_at=datetime.utcnow(),
        window_hours=window_hours,
        enabled=alert_policy.enabled,
        snapshot=WriterTaskAlertSnapshot(
            queued_count=queued_count,
            running_count=running_count,
            stale_running_count=stale_running_count,
            finished_recent_count=finished_recent_count,
            failed_recent_count=failed_recent_count,
            timeout_recent_count=timeout_recent_count,
            failure_rate_percent=failure_rate_percent,
        ),
        failure_top=failure_top_items,
        channels=channels,
        issues=issues,
    )


@router.get("/writer-task-queue", response_model=WriterTaskQueueResponse)
async def get_writer_task_queue(
    limit: int = 100,
    status_group: Literal["active", "failed", "all"] = "active",
    project_id: Optional[str] = None,
    user_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(get_current_admin),
) -> WriterTaskQueueResponse:
    """返回写作任务队列视图（基于 generation_tasks 持久化任务）。"""
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1~500 之间")

    task_types = [TASK_TYPE_CHAPTER_GENERATION, TASK_TYPE_BLUEPRINT_GENERATION]
    active_statuses = {TASK_STATUS_QUEUED, TASK_STATUS_RUNNING}
    failed_statuses = {TASK_STATUS_FAILED, TASK_STATUS_CANCELED}
    now_utc = datetime.now(timezone.utc)

    def _queue_state(task_status: str) -> str:
        if task_status in active_statuses:
            return "active"
        if task_status in failed_statuses:
            return "failed"
        if task_status == TASK_STATUS_COMPLETED:
            return "done"
        return "other"

    def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if getattr(dt, "tzinfo", None) is None:
            return dt
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    def _age_seconds(dt: Optional[datetime]) -> int:
        if not dt:
            return 0
        value = dt if getattr(dt, "tzinfo", None) is not None else dt.replace(tzinfo=timezone.utc)
        return max(0, int((now_utc - value).total_seconds()))

    def _duration_seconds(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
        if not start or not end:
            return None
        start_dt = start if getattr(start, "tzinfo", None) is not None else start.replace(tzinfo=timezone.utc)
        end_dt = end if getattr(end, "tzinfo", None) is not None else end.replace(tzinfo=timezone.utc)
        seconds = (end_dt - start_dt).total_seconds()
        if seconds < 0:
            return None
        # 防止脏数据拉高统计
        return min(seconds, 7 * 24 * 3600)

    def _parse_datetime_value(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            if text.endswith("Z"):
                text = f"{text[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(text)
            except ValueError:
                return None
        else:
            return None
        if getattr(dt, "tzinfo", None) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    base_filters = [GenerationTask.task_type.in_(task_types)]
    if project_id:
        base_filters.append(GenerationTask.project_id == project_id)
    if user_id is not None:
        base_filters.append(GenerationTask.user_id == user_id)

    status_rows = (
        await session.execute(
            select(GenerationTask.status, func.count(GenerationTask.id))
            .where(*base_filters)
            .group_by(GenerationTask.status)
        )
    ).all()
    status_counts_all = {str(row[0] or "unknown"): int(row[1] or 0) for row in status_rows}

    running_rows = (
        await session.execute(
            select(
                GenerationTask.heartbeat_at,
                GenerationTask.updated_at,
                GenerationTask.started_at,
                GenerationTask.created_at,
            ).where(*base_filters, GenerationTask.status == TASK_STATUS_RUNNING)
        )
    ).all()
    running_age_minutes_values: list[int] = []
    stale_running_count = 0
    for heartbeat_at, updated_at, started_at, created_at in running_rows:
        running_anchor = started_at or updated_at or created_at
        running_age_minutes_values.append(_age_seconds(running_anchor) // 60)
        heartbeat_anchor = heartbeat_at or updated_at or started_at or created_at
        if _age_seconds(heartbeat_anchor) >= _WRITER_TASK_HEARTBEAT_TIMEOUT_SECONDS:
            stale_running_count += 1
    avg_running_age_minutes = (
        round(sum(running_age_minutes_values) / len(running_age_minutes_values), 2)
        if running_age_minutes_values
        else 0.0
    )

    recent_window_since = now_utc - timedelta(hours=_WRITER_TASK_RECENT_WINDOW_HOURS)
    recent_rows = (
        await session.execute(
            select(
                GenerationTask.status,
                GenerationTask.started_at,
                GenerationTask.finished_at,
                GenerationTask.created_at,
            ).where(
                *base_filters,
                GenerationTask.finished_at.is_not(None),
                GenerationTask.finished_at >= recent_window_since,
            )
        )
    ).all()
    recent_finished_count = len(recent_rows)
    recent_failed_count = sum(1 for status, _, _, _ in recent_rows if str(status or "") in failed_statuses)
    recent_failure_rate_percent = (
        round((recent_failed_count * 100.0) / recent_finished_count, 2)
        if recent_finished_count > 0
        else 0.0
    )
    recent_durations = [
        value
        for _, started_at, finished_at, created_at in recent_rows
        for value in [_duration_seconds(started_at or created_at, finished_at)]
        if value is not None
    ]
    recent_avg_duration_seconds = (
        round(sum(recent_durations) / len(recent_durations), 2)
        if recent_durations
        else 0.0
    )
    if recent_durations:
        sorted_durations = sorted(recent_durations)
        p95_index = max(0, min(len(sorted_durations) - 1, math.ceil(len(sorted_durations) * 0.95) - 1))
        recent_p95_duration_seconds = round(sorted_durations[p95_index], 2)
    else:
        recent_p95_duration_seconds = 0.0

    failure_rows = (
        await session.execute(
            select(
                GenerationTask.error_message,
                GenerationTask.status_message,
            )
            .where(*base_filters, GenerationTask.status.in_(failed_statuses))
            .order_by(GenerationTask.updated_at.desc())
            .limit(400)
        )
    ).all()
    failure_counter: dict[str, tuple[str, int]] = {}
    for error_message, status_message in failure_rows:
        message = str(error_message or status_message or "任务失败").strip()
        key = message.splitlines()[0][:140] or "任务失败"
        sample = message[:260] or key
        previous = failure_counter.get(key)
        if not previous:
            failure_counter[key] = (sample, 1)
        else:
            failure_counter[key] = (previous[0], previous[1] + 1)
    failure_top = sorted(failure_counter.items(), key=lambda item: item[1][1], reverse=True)[:8]
    failure_top_items = [
        WriterTaskFailureTopItem(error_key=key, sample_message=meta[0], count=meta[1]) for key, meta in failure_top
    ]

    stmt = (
        select(
            GenerationTask,
            NovelProject.title,
            NovelProject.user_id,
            User.username,
        )
        .join(NovelProject, GenerationTask.project_id == NovelProject.id)
        .join(User, NovelProject.user_id == User.id, isouter=True)
        .where(*base_filters)
    )

    if status_group == "active":
        stmt = stmt.where(GenerationTask.status.in_(active_statuses))
    elif status_group == "failed":
        stmt = stmt.where(GenerationTask.status.in_(failed_statuses))

    stmt = stmt.order_by(GenerationTask.updated_at.desc(), GenerationTask.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).all()

    chapter_meta_map: dict[tuple[str, int], Chapter] = {}
    project_ids = {str(task.project_id) for task, _, _, _ in rows if task.chapter_number is not None}
    chapter_numbers = {int(task.chapter_number) for task, _, _, _ in rows if task.chapter_number is not None}
    if project_ids and chapter_numbers:
        chapter_rows = (
            await session.execute(
                select(Chapter).where(
                    Chapter.project_id.in_(project_ids),
                    Chapter.chapter_number.in_(chapter_numbers),
                )
            )
        ).scalars().all()
        chapter_meta_map = {(str(chapter.project_id), int(chapter.chapter_number)): chapter for chapter in chapter_rows}

    items: list[WriterTaskQueueItem] = []

    for task, project_title, owner_user_id, owner_username in rows:
        status_value = (task.status or "unknown").strip() or "unknown"
        queue_state = _queue_state(status_value)

        chapter_key = (
            (str(task.project_id), int(task.chapter_number))
            if task.chapter_number is not None
            else None
        )
        chapter_meta = chapter_meta_map.get(chapter_key) if chapter_key else None

        updated_at = task.updated_at or task.created_at or now_utc
        age_anchor = (
            task.started_at if status_value == TASK_STATUS_RUNNING and task.started_at else updated_at
        )
        age_minutes = _age_seconds(age_anchor) // 60

        heartbeat_age_seconds: Optional[int] = None
        heartbeat_at = task.heartbeat_at
        if status_value == TASK_STATUS_RUNNING:
            heartbeat_anchor = heartbeat_at or updated_at or task.started_at or task.created_at
            heartbeat_age_seconds = _age_seconds(heartbeat_anchor)

        checkpoint = task.checkpoint if isinstance(task.checkpoint, dict) else {}
        stage_timeline_raw = checkpoint.get("stage_timeline")
        stage_timeline: list[dict] = []
        if isinstance(stage_timeline_raw, list):
            for item in stage_timeline_raw[-16:]:
                if not isinstance(item, dict):
                    continue
                stage_name = str(item.get("stage") or "").strip()
                if not stage_name:
                    continue
                entered_at = _parse_datetime_value(item.get("entered_at") or item.get("updated_at"))
                updated_at_stage = _parse_datetime_value(item.get("updated_at") or item.get("entered_at"))
                stage_timeline.append(
                    {
                        "stage": stage_name,
                        "entered_at": entered_at.isoformat() if entered_at else None,
                        "updated_at": updated_at_stage.isoformat() if updated_at_stage else None,
                        "progress_percent": int(item.get("progress_percent") or 0),
                    }
                )

        execution_meta = task.result if isinstance(task.result, dict) else {}
        execution_info = execution_meta.get("execution") if isinstance(execution_meta.get("execution"), dict) else {}
        run_seconds_raw = execution_info.get("duration_seconds")
        try:
            run_seconds = float(run_seconds_raw) if run_seconds_raw is not None else None
        except (TypeError, ValueError):
            run_seconds = None
        if run_seconds is None:
            run_anchor_end = task.finished_at or now_utc
            run_seconds = _duration_seconds(task.started_at or task.created_at, run_anchor_end)
            if run_seconds is not None:
                run_seconds = round(float(run_seconds), 2)

        current_stage_seconds: Optional[float] = None
        if stage_timeline:
            last_stage = stage_timeline[-1]
            stage_start_dt = _parse_datetime_value(last_stage.get("entered_at"))
            if stage_start_dt:
                stage_end_dt = task.finished_at if status_value in {TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_CANCELED} else now_utc
                stage_end_dt = stage_end_dt if getattr(stage_end_dt, "tzinfo", None) is not None else stage_end_dt.replace(tzinfo=timezone.utc)
                if stage_end_dt >= stage_start_dt:
                    current_stage_seconds = round((stage_end_dt - stage_start_dt).total_seconds(), 2)

        llm_metrics = execution_meta.get("llm_metrics") if isinstance(execution_meta.get("llm_metrics"), dict) else {}
        llm_call_count = int(llm_metrics.get("call_count") or 0)
        llm_success_count = int(llm_metrics.get("success_count") or 0)
        llm_error_count = int(llm_metrics.get("error_count") or 0)
        llm_top_model = str(llm_metrics.get("top_model") or "").strip() or None
        llm_top_provider = str(llm_metrics.get("top_provider") or "").strip() or None
        llm_avg_latency_raw = llm_metrics.get("avg_latency_ms")
        try:
            llm_avg_latency_ms = round(float(llm_avg_latency_raw), 2) if llm_avg_latency_raw is not None else None
        except (TypeError, ValueError):
            llm_avg_latency_ms = None

        consistency_guard_status = None
        consistency_guard_message = None
        guard_meta = execution_meta.get("consistency_guard") if isinstance(execution_meta.get("consistency_guard"), dict) else {}
        if guard_meta:
            consistency_guard_status = str(guard_meta.get("status") or "").strip() or None
            consistency_guard_message = str(guard_meta.get("message") or guard_meta.get("summary") or "").strip() or None

        items.append(
            WriterTaskQueueItem(
                task_id=task.id,
                task_type=task.task_type,
                chapter_id=chapter_meta.id if chapter_meta else None,
                project_id=task.project_id,
                project_title=str(project_title or task.project_id),
                chapter_number=task.chapter_number,
                status=status_value,
                queue_state=queue_state,
                owner_user_id=int(owner_user_id),
                owner_username=str(owner_username) if owner_username else None,
                progress_percent=max(0, min(100, int(task.progress_percent or 0))),
                stage_label=task.stage_label,
                status_message=task.status_message,
                error_message=task.error_message,
                retry_count=max(0, int(task.retry_count or 0)),
                word_count=chapter_meta.word_count or 0 if chapter_meta else 0,
                selected_version_id=chapter_meta.selected_version_id if chapter_meta else None,
                heartbeat_at=_to_naive_utc(heartbeat_at),
                heartbeat_age_seconds=heartbeat_age_seconds,
                updated_at=_to_naive_utc(updated_at) or datetime.utcnow(),
                age_minutes=age_minutes,
                run_seconds=run_seconds,
                current_stage_seconds=current_stage_seconds,
                stage_timeline=stage_timeline,
                llm_call_count=llm_call_count,
                llm_success_count=llm_success_count,
                llm_error_count=llm_error_count,
                llm_avg_latency_ms=llm_avg_latency_ms,
                llm_top_model=llm_top_model,
                llm_top_provider=llm_top_provider,
                consistency_guard_status=consistency_guard_status,
                consistency_guard_message=consistency_guard_message,
            )
        )

    logger.info(
        "管理员读取写作任务队列：group=%s count=%s project_id=%s user_id=%s",
        status_group,
        len(items),
        project_id,
        user_id,
    )
    summary = WriterTaskQueueSummary(
        queued_count=int(status_counts_all.get(TASK_STATUS_QUEUED, 0)),
        running_count=int(status_counts_all.get(TASK_STATUS_RUNNING, 0)),
        completed_count=int(status_counts_all.get(TASK_STATUS_COMPLETED, 0)),
        failed_count=int(status_counts_all.get(TASK_STATUS_FAILED, 0)),
        canceled_count=int(status_counts_all.get(TASK_STATUS_CANCELED, 0)),
        stale_running_count=stale_running_count,
        avg_running_age_minutes=avg_running_age_minutes,
        recent_window_hours=_WRITER_TASK_RECENT_WINDOW_HOURS,
        recent_finished_count=recent_finished_count,
        recent_failed_count=recent_failed_count,
        recent_failure_rate_percent=recent_failure_rate_percent,
        recent_avg_duration_seconds=recent_avg_duration_seconds,
        recent_p95_duration_seconds=recent_p95_duration_seconds,
    )
    return WriterTaskQueueResponse(
        total=len(items),
        status_group=status_group,
        status_counts=status_counts_all,
        heartbeat_timeout_seconds=_WRITER_TASK_HEARTBEAT_TIMEOUT_SECONDS,
        summary=summary,
        failure_top=failure_top_items,
        items=items,
    )


@router.post("/writer-task-queue/retry", response_model=WriterTaskRetryResponse)
async def retry_writer_task(
    payload: WriterTaskRetryRequest,
    session: AsyncSession = Depends(get_session),
    current_admin=Depends(get_current_admin),
) -> WriterTaskRetryResponse:
    """管理员重试写作队列任务（异步投递）。"""
    row = (
        await session.execute(
            select(
                Chapter,
                NovelProject.user_id,
            )
            .join(NovelProject, Chapter.project_id == NovelProject.id)
            .where(Chapter.id == payload.chapter_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="章节任务不存在")

    chapter = row[0]
    owner_user_id = int(row[1])
    previous_status = (chapter.status or "unknown").strip() or "unknown"

    if chapter.id in _WRITER_RETRY_INFLIGHT:
        raise HTTPException(status_code=409, detail="该任务已在重试队列中")

    if previous_status in _WRITER_ACTIVE_STATUSES and not payload.force:
        raise HTTPException(status_code=409, detail="任务正在执行中，若需强制重试请开启 force")

    if previous_status not in _WRITER_FAILED_STATUSES and not payload.force:
        raise HTTPException(status_code=400, detail="当前任务非失败状态，若需重试请开启 force")

    dispatched_action = _resolve_retry_action(payload.retry_mode, previous_status)

    if dispatched_action == "generate":
        outline_count = int(
            await session.scalar(
                select(func.count(ChapterOutline.id)).where(
                    ChapterOutline.project_id == chapter.project_id,
                    ChapterOutline.chapter_number == chapter.chapter_number,
                )
            )
            or 0
        )
        if outline_count <= 0:
            raise HTTPException(status_code=400, detail="缺少章节大纲，无法重试生成")
        chapter.status = "generating"
    else:
        version_count = int(
            await session.scalar(
                select(func.count(ChapterVersion.id)).where(ChapterVersion.chapter_id == chapter.id)
            )
            or 0
        )
        if chapter.selected_version_id is None and version_count <= 0:
            raise HTTPException(status_code=400, detail="章节没有可评审版本，无法重试评审")
        chapter.status = "evaluating"

    await session.commit()

    _WRITER_RETRY_INFLIGHT.add(chapter.id)
    asyncio.create_task(
        _run_writer_retry_task(
            chapter_id=chapter.id,
            action=dispatched_action,
            writing_notes=payload.writing_notes,
            trigger_admin_id=int(current_admin.id),
        )
    )

    logger.info(
        "管理员投递重试任务：admin_id=%s chapter_id=%s project_id=%s chapter=%s owner_user_id=%s action=%s force=%s",
        current_admin.id,
        chapter.id,
        chapter.project_id,
        chapter.chapter_number,
        owner_user_id,
        dispatched_action,
        payload.force,
    )
    action_label = "重试生成" if dispatched_action == "generate" else "重试评审"
    return WriterTaskRetryResponse(
        accepted=True,
        chapter_id=chapter.id,
        project_id=chapter.project_id,
        chapter_number=chapter.chapter_number,
        previous_status=previous_status,
        dispatched_action=dispatched_action,
        message=f"{action_label}已投递，稍后刷新队列查看结果",
    )


@router.get("/users", response_model=List[UserSchema])
async def list_users(
    service: UserService = Depends(get_user_service),
    _: None = Depends(get_current_admin),
) -> List[UserSchema]:
    users = await service.list_users()
    logger.info("管理员请求用户列表，共 %s 条", len(users))
    return [UserSchema.model_validate(user) for user in users]


@router.post("/users", response_model=UserSchema, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreateAdmin,
    service: UserService = Depends(get_user_service),
    current_admin=Depends(get_current_admin),
) -> UserSchema:
    try:
        user = await service.create_user_admin(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info("管理员 %s 创建用户：%s", current_admin.username, user.id)
    return UserSchema.model_validate(user)


@router.get("/users/{user_id}", response_model=UserSchema)
async def get_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
    _: None = Depends(get_current_admin),
) -> UserSchema:
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserSchema.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserSchema)
async def update_user(
    user_id: int,
    payload: UserUpdateAdmin,
    service: UserService = Depends(get_user_service),
    current_admin=Depends(get_current_admin),
) -> UserSchema:
    try:
        user = await service.update_user_admin(user_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    logger.info("管理员 %s 更新用户：%s", current_admin.username, user_id)
    return UserSchema.model_validate(user)


@router.get("/users/{user_id}/subscription", response_model=UserSubscriptionRead)
async def get_user_subscription(
    user_id: int,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    _: None = Depends(get_current_admin),
) -> UserSubscriptionRead:
    return await service.get_user_subscription(user_id)


@router.put("/users/{user_id}/subscription", response_model=UserSubscriptionRead)
async def upsert_user_subscription(
    user_id: int,
    payload: UserSubscriptionUpsert,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_admin=Depends(get_current_admin),
) -> UserSubscriptionRead:
    item = await service.upsert_user_subscription(
        user_id,
        payload,
        actor_user_id=current_admin.id,
        actor_username=current_admin.username,
    )
    logger.info(
        "管理员 %s 更新用户订阅：user_id=%s plan=%s status=%s",
        current_admin.username,
        user_id,
        item.plan_name,
        item.status,
    )
    return item


@router.post("/users/{user_id}/subscription/compensation", response_model=UserSubscriptionCompensationRead)
async def compensate_user_subscription_request_quota(
    user_id: int,
    payload: UserSubscriptionCompensationRequest,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_admin=Depends(get_current_admin),
) -> UserSubscriptionCompensationRead:
    result = await service.apply_request_compensation(
        user_id,
        request_quota=payload.request_quota,
        note=payload.note,
        actor_user_id=current_admin.id,
        actor_username=current_admin.username,
    )
    logger.info(
        "管理员 %s 补偿用户请求额度：user_id=%s quota=%s note=%s",
        current_admin.username,
        user_id,
        payload.request_quota,
        payload.note,
    )
    return result


@router.get("/subscription-audits", response_model=List[UserSubscriptionAuditRead])
async def list_subscription_audits(
    user_id: Optional[int] = None,
    limit: int = 100,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    _: None = Depends(get_current_admin),
) -> List[UserSubscriptionAuditRead]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1~500 之间")
    return await service.list_audit_logs(user_id=user_id, limit=limit)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
    current_admin=Depends(get_current_admin),
) -> None:
    try:
        deleted = await service.delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="用户不存在")
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    logger.info("管理员 %s 删除用户：%s", current_admin.username, user_id)


@router.get("/novel-projects", response_model=List[AdminNovelSummary])
async def list_novel_projects(
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> List[AdminNovelSummary]:
    projects = await service.list_projects_for_admin()
    logger.info("管理员查看项目列表，共 %s 个", len(projects))
    return projects


@router.get("/novel-projects/{project_id}", response_model=NovelProjectSchema)
async def get_novel_project(
    project_id: str,
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> NovelProjectSchema:
    logger.info("管理员查看项目详情：%s", project_id)
    return await service.get_project_schema_for_admin(project_id)


@router.get("/novel-projects/{project_id}/sections/{section}", response_model=NovelSectionResponse)
async def get_novel_project_section(
    project_id: str,
    section: NovelSectionType,
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> NovelSectionResponse:
    logger.info("管理员查看项目 %s 的 %s 区段", project_id, section)
    return await service.get_section_data_for_admin(project_id, section)


@router.get("/novel-projects/{project_id}/chapters/{chapter_number}", response_model=ChapterSchema)
async def get_novel_project_chapter(
    project_id: str,
    chapter_number: int,
    service: NovelService = Depends(get_novel_service),
    _: None = Depends(get_current_admin),
) -> ChapterSchema:
    logger.info("管理员查看项目 %s 第 %s 章详情", project_id, chapter_number)
    return await service.get_chapter_schema_for_admin(project_id, chapter_number)


@router.get("/prompts", response_model=List[PromptRead])
async def list_prompts(
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> List[PromptRead]:
    prompts = await service.list_prompts()
    logger.info("管理员请求提示词列表，共 %s 条", len(prompts))
    return prompts


@router.post("/prompts", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def create_prompt(
    payload: PromptCreate,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> PromptRead:
    prompt = await service.create_prompt(payload)
    logger.info("管理员创建提示词：%s", prompt.id)
    return prompt


@router.get("/prompts/presets", response_model=List[WritingPresetRead])
async def list_prompt_presets(
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> List[WritingPresetRead]:
    presets = await service.list_writing_presets()
    logger.info("管理员获取写作预设列表，共 %s 条", len(presets))
    return presets


@router.post("/prompts/presets", response_model=WritingPresetRead)
async def upsert_prompt_preset(
    payload: WritingPresetUpsert,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> WritingPresetRead:
    try:
        preset = await service.upsert_writing_preset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("管理员写入写作预设：%s", preset.preset_id)
    return preset


@router.put("/prompts/presets/active", response_model=Optional[WritingPresetRead])
async def activate_prompt_preset(
    payload: WritingPresetActivateRequest,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> Optional[WritingPresetRead]:
    try:
        preset = await service.activate_writing_preset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("管理员切换写作预设：active=%s", payload.preset_id or "")
    return preset


@router.delete("/prompts/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_preset(
    preset_id: str,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> None:
    try:
        deleted = await service.delete_writing_preset(preset_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="写作预设不存在")
    logger.info("管理员删除写作预设：%s", preset_id)


@router.get("/prompts/{prompt_id}", response_model=PromptRead)
async def get_prompt(
    prompt_id: int,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> PromptRead:
    prompt = await service.get_prompt_by_id(prompt_id)
    if not prompt:
        logger.warning("提示词 %s 不存在", prompt_id)
        raise HTTPException(status_code=404, detail="提示词不存在")
    logger.info("管理员获取提示词：%s", prompt_id)
    return prompt


@router.patch("/prompts/{prompt_id}", response_model=PromptRead)
async def update_prompt(
    prompt_id: int,
    payload: PromptUpdate,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> PromptRead:
    result = await service.update_prompt(prompt_id, payload)
    if not result:
        logger.warning("提示词 %s 不存在，无法更新", prompt_id)
        raise HTTPException(status_code=404, detail="提示词不存在")
    logger.info("管理员更新提示词：%s", prompt_id)
    return result


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: int,
    service: PromptService = Depends(get_prompt_service),
    _: None = Depends(get_current_admin),
) -> None:
    deleted = await service.delete_prompt(prompt_id)
    if not deleted:
        logger.warning("提示词 %s 不存在，无法删除", prompt_id)
        raise HTTPException(status_code=404, detail="提示词不存在")
    logger.info("管理员删除提示词：%s", prompt_id)


@router.get("/update-logs", response_model=List[UpdateLogRead])
async def list_update_logs(
    service: UpdateLogService = Depends(get_update_log_service),
    _: None = Depends(get_current_admin),
) -> List[UpdateLogRead]:
    logs = await service.list_logs()
    logger.info("管理员查看更新日志列表，共 %s 条", len(logs))
    return [UpdateLogRead.model_validate(log) for log in logs]


@router.post("/update-logs", response_model=UpdateLogRead, status_code=status.HTTP_201_CREATED)
async def create_update_log(
    payload: UpdateLogCreate,
    service: UpdateLogService = Depends(get_update_log_service),
    current_admin=Depends(get_current_admin),
) -> UpdateLogRead:
    log = await service.create_log(
        payload.content,
        creator=current_admin.username,
        is_pinned=payload.is_pinned or False,
    )
    logger.info("管理员 %s 创建更新日志：%s", current_admin.username, log.id)
    return UpdateLogRead.model_validate(log)


@router.delete("/update-logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_update_log(
    log_id: int,
    service: UpdateLogService = Depends(get_update_log_service),
    _: None = Depends(get_current_admin),
) -> None:
    await service.delete_log(log_id)
    logger.info("管理员删除更新日志：%s", log_id)


@router.patch("/update-logs/{log_id}", response_model=UpdateLogRead)
async def update_update_log(
    log_id: int,
    payload: UpdateLogUpdate,
    service: UpdateLogService = Depends(get_update_log_service),
    _: None = Depends(get_current_admin),
) -> UpdateLogRead:
    log = await service.update_log(
        log_id,
        content=payload.content,
        is_pinned=payload.is_pinned,
    )
    logger.info("管理员更新日志 %s", log_id)
    return UpdateLogRead.model_validate(log)


@router.get("/settings/daily-request-limit", response_model=DailyRequestLimit)
async def get_daily_limit(
    service: AdminSettingService = Depends(get_admin_setting_service),
    _: None = Depends(get_current_admin),
) -> DailyRequestLimit:
    value = await service.get("daily_request_limit", "100")
    logger.info("管理员查询每日请求上限：%s", value)
    return DailyRequestLimit(limit=int(value or 100))


@router.put("/settings/daily-request-limit", response_model=DailyRequestLimit)
async def update_daily_limit(
    payload: DailyRequestLimit,
    service: AdminSettingService = Depends(get_admin_setting_service),
    _: None = Depends(get_current_admin),
) -> DailyRequestLimit:
    await service.set("daily_request_limit", str(payload.limit))
    logger.info("管理员设置每日请求上限为 %s", payload.limit)
    return payload


@router.get("/system-configs", response_model=List[SystemConfigRead])
async def list_system_configs(
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> List[SystemConfigRead]:
    configs = await service.list_configs()
    logger.info("管理员获取系统配置，共 %s 条", len(configs))
    return configs


@router.get("/system-configs/{key}", response_model=SystemConfigRead)
async def get_system_config(
    key: str,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> SystemConfigRead:
    config = await service.get_config(key)
    if not config:
        logger.warning("系统配置 %s 不存在", key)
        raise HTTPException(status_code=404, detail="配置项不存在")
    logger.info("管理员查询系统配置：%s", key)
    return config


@router.put("/system-configs/{key}", response_model=SystemConfigRead)
async def upsert_system_config(
    key: str,
    payload: SystemConfigCreate,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> SystemConfigRead:
    logger.info("管理员写入系统配置：%s", key)
    return await service.upsert_config(
        SystemConfigCreate(key=key, value=payload.value, description=payload.description)
    )


@router.patch("/system-configs/{key}", response_model=SystemConfigRead)
async def patch_system_config(
    key: str,
    payload: SystemConfigUpdate,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> SystemConfigRead:
    config = await service.patch_config(key, payload)
    if not config:
        logger.warning("系统配置 %s 不存在，无法更新", key)
        raise HTTPException(status_code=404, detail="配置项不存在")
    logger.info("管理员部分更新系统配置：%s", key)
    return config


@router.delete("/system-configs/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_system_config(
    key: str,
    service: ConfigService = Depends(get_config_service),
    _: None = Depends(get_current_admin),
) -> None:
    deleted = await service.remove_config(key)
    if not deleted:
        logger.warning("系统配置 %s 不存在，无法删除", key)
        raise HTTPException(status_code=404, detail="配置项不存在")
    logger.info("管理员删除系统配置：%s", key)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    current_admin=Depends(get_current_admin),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.change_password(current_admin.username, payload.old_password, payload.new_password)
    logger.info("管理员 %s 修改密码", current_admin.username)
