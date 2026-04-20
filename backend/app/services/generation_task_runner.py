# AIMETA P=任务队列执行器_持久化任务调度|R=排队执行_重启恢复_取消|NR=不含HTTP接口|E=GenerationTaskRunner|X=job|A=队列执行器|D=asyncio,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select, update

from ..core.config import settings
from ..db.session import AsyncSessionLocal
from ..models.llm_call_log import LLMCallLog
from ..models.novel import Chapter, ChapterVersion
from ..models.system_config import SystemConfig
from .consistency_service import ConsistencyService
from .blueprint_generation_service import generate_blueprint_for_project
from .generation_task_service import (
    TASK_STATUS_CANCELED,
    TASK_STATUS_FAILED,
    TASK_TYPE_BLUEPRINT_GENERATION,
    TASK_TYPE_CHAPTER_GENERATION,
    GenerationTaskService,
)
from .generation_alert_service import GenerationAlertService
from .llm_service import LLMService
from .novel_service import NovelService
from .pipeline_orchestrator import PipelineOrchestrator
from ..utils.task_failure import classify_task_failure, failure_category_label

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyGuardPolicy:
    enabled: bool
    min_severity: str
    auto_fix: bool
    auto_select_fixed: bool
    max_violations: int


class GenerationTaskRunner:
    def __init__(self) -> None:
        self._worker_count = self._clamp_int(
            settings.generation_task_workers,
            default=1,
            min_value=1,
            max_value=4,
        )
        self._heartbeat_interval_seconds = self._clamp_int(
            settings.generation_task_heartbeat_interval_seconds,
            default=10,
            min_value=3,
            max_value=180,
        )
        self._stale_timeout_seconds = self._clamp_int(
            settings.generation_task_stale_timeout_seconds,
            default=300,
            min_value=30,
            max_value=3600,
        )
        self._stale_scan_interval_seconds = self._clamp_int(
            settings.generation_task_stale_scan_interval_seconds,
            default=30,
            min_value=10,
            max_value=600,
        )
        self._chapter_timeout_seconds = self._clamp_int(
            settings.generation_task_chapter_timeout_seconds,
            default=1800,
            min_value=120,
            max_value=6 * 3600,
        )
        self._blueprint_timeout_seconds = self._clamp_int(
            settings.generation_task_blueprint_timeout_seconds,
            default=1200,
            min_value=120,
            max_value=6 * 3600,
        )
        self._default_max_retries = self._clamp_int(
            settings.generation_task_auto_retry_max,
            default=1,
            min_value=0,
            max_value=6,
        )
        self._retry_backoff_base_seconds = self._clamp_int(
            settings.generation_task_retry_backoff_base_seconds,
            default=8,
            min_value=1,
            max_value=300,
        )
        self._retry_backoff_max_seconds = self._clamp_int(
            settings.generation_task_retry_backoff_max_seconds,
            default=180,
            min_value=1,
            max_value=3600,
        )
        self._policy_refresh_interval_seconds = self._clamp_int(
            settings.generation_task_policy_refresh_interval_seconds,
            default=30,
            min_value=5,
            max_value=600,
        )

        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._queued_task_ids: set[str] = set()
        self._workers: list[asyncio.Task] = []
        self._running_handles: dict[str, asyncio.Task] = {}
        self._delayed_enqueue_handles: set[asyncio.Task] = set()
        self._stale_scan_handle: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()
        self._policy_refresh_lock = asyncio.Lock()
        self._next_policy_refresh_at = 0.0

    @staticmethod
    def _parse_bool(raw: Any, default: bool) -> bool:
        if raw is None:
            return default
        normalized = str(raw).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _normalize_severity(raw: Any, default: str = "major") -> str:
        value = str(raw or "").strip().lower()
        if value in {"critical", "major", "minor"}:
            return value
        return default

    @staticmethod
    def _severity_rank(level: str) -> int:
        mapping = {"critical": 1, "major": 2, "minor": 3}
        return mapping.get(str(level).strip().lower(), 3)

    async def _resolve_consistency_guard_policy(self, session) -> ConsistencyGuardPolicy:
        keys = {
            "writer.consistency_guard.enabled": "true",
            "writer.consistency_guard.min_severity": "major",
            "writer.consistency_guard.auto_fix": "true",
            "writer.consistency_guard.auto_select_fixed": "true",
            "writer.consistency_guard.max_violations": "12",
        }
        rows = (
            await session.execute(
                select(SystemConfig.key, SystemConfig.value).where(SystemConfig.key.in_(list(keys.keys())))
            )
        ).all()
        values = {str(key): value for key, value in rows}

        raw_max_violations = values.get("writer.consistency_guard.max_violations", keys["writer.consistency_guard.max_violations"])
        try:
            max_violations = max(1, min(50, int(str(raw_max_violations).strip())))
        except Exception:
            max_violations = 12

        return ConsistencyGuardPolicy(
            enabled=self._parse_bool(values.get("writer.consistency_guard.enabled"), True),
            min_severity=self._normalize_severity(
                values.get("writer.consistency_guard.min_severity"),
                default="major",
            ),
            auto_fix=self._parse_bool(values.get("writer.consistency_guard.auto_fix"), True),
            auto_select_fixed=self._parse_bool(
                values.get("writer.consistency_guard.auto_select_fixed"),
                True,
            ),
            max_violations=max_violations,
        )

    def _filter_guard_violations(
        self,
        violations: list[Any],
        *,
        min_severity: str,
        limit: int,
    ) -> list[Any]:
        threshold = self._severity_rank(min_severity)
        selected: list[Any] = []
        for item in violations:
            severity_value = item.severity.value if hasattr(item.severity, "value") else str(item.severity)
            if self._severity_rank(severity_value) <= threshold:
                selected.append(item)
            if len(selected) >= limit:
                break
        return selected

    def _format_consistency_report(self, result: Any) -> Dict[str, Any]:
        return {
            "is_consistent": bool(result.is_consistent),
            "summary": str(result.summary or "").strip(),
            "check_time_ms": int(getattr(result, "check_time_ms", 0) or 0),
            "violations": [
                {
                    "severity": item.severity.value if hasattr(item.severity, "value") else str(item.severity),
                    "category": item.category,
                    "description": item.description,
                    "location": item.location,
                    "suggested_fix": item.suggested_fix,
                    "confidence": float(item.confidence or 0.0),
                }
                for item in (result.violations or [])
            ],
        }

    async def _collect_task_llm_metrics(
        self,
        *,
        project_id: str,
        user_id: int,
        started_at: Optional[datetime],
        finished_at: datetime,
    ) -> Dict[str, Any]:
        if started_at is None:
            return {
                "call_count": 0,
                "success_count": 0,
                "error_count": 0,
                "avg_latency_ms": None,
                "top_model": None,
                "top_provider": None,
            }

        start = started_at if getattr(started_at, "tzinfo", None) is not None else started_at.replace(tzinfo=timezone.utc)
        end = finished_at if getattr(finished_at, "tzinfo", None) is not None else finished_at.replace(tzinfo=timezone.utc)
        if end < start:
            end = start

        start_window = start.replace(microsecond=0)
        end_window = end.replace(microsecond=0)
        # 加 8 秒缓冲，覆盖少量日志写入延迟
        end_window = end_window + timedelta(seconds=8)

        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(
                        LLMCallLog.status,
                        LLMCallLog.model,
                        LLMCallLog.provider,
                        LLMCallLog.latency_ms,
                    ).where(
                        LLMCallLog.project_id == project_id,
                        LLMCallLog.user_id == user_id,
                        LLMCallLog.created_at >= start_window,
                        LLMCallLog.created_at <= end_window,
                    )
                )
            ).all()

        total = len(rows)
        success_count = sum(1 for status, _, _, _ in rows if str(status or "").strip().lower() == "success")
        error_count = total - success_count
        latency_values = [
            int(latency_ms)
            for status, _, _, latency_ms in rows
            if str(status or "").strip().lower() == "success" and latency_ms is not None
        ]
        avg_latency_ms = round(sum(latency_values) / len(latency_values), 2) if latency_values else None

        model_counter: Dict[str, int] = {}
        provider_counter: Dict[str, int] = {}
        for _, model, provider, _ in rows:
            model_key = str(model or "").strip()
            provider_key = str(provider or "").strip()
            if model_key:
                model_counter[model_key] = model_counter.get(model_key, 0) + 1
            if provider_key:
                provider_counter[provider_key] = provider_counter.get(provider_key, 0) + 1

        top_model = max(model_counter.items(), key=lambda item: item[1])[0] if model_counter else None
        top_provider = max(provider_counter.items(), key=lambda item: item[1])[0] if provider_counter else None
        return {
            "call_count": total,
            "success_count": success_count,
            "error_count": error_count,
            "avg_latency_ms": avg_latency_ms,
            "top_model": top_model,
            "top_provider": top_provider,
        }

    @staticmethod
    def _clamp_int(value: Any, *, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(min_value, min(max_value, parsed))

    @staticmethod
    def _policy_specs() -> tuple[tuple[str, str, int, int], ...]:
        return (
            ("generation.task.worker_count", "_worker_count", 1, 4),
            ("generation.task.heartbeat_interval_seconds", "_heartbeat_interval_seconds", 3, 180),
            ("generation.task.stale_timeout_seconds", "_stale_timeout_seconds", 30, 3600),
            ("generation.task.stale_scan_interval_seconds", "_stale_scan_interval_seconds", 10, 600),
            ("generation.task.chapter_timeout_seconds", "_chapter_timeout_seconds", 120, 6 * 3600),
            ("generation.task.blueprint_timeout_seconds", "_blueprint_timeout_seconds", 120, 6 * 3600),
            ("generation.task.auto_retry_max", "_default_max_retries", 0, 6),
            ("generation.task.retry_backoff_base_seconds", "_retry_backoff_base_seconds", 1, 300),
            ("generation.task.retry_backoff_max_seconds", "_retry_backoff_max_seconds", 1, 3600),
            ("generation.task.policy_refresh_interval_seconds", "_policy_refresh_interval_seconds", 5, 600),
        )

    def _runtime_policy_snapshot(self) -> Dict[str, int]:
        return {
            "worker_count": self._worker_count,
            "heartbeat_interval_seconds": self._heartbeat_interval_seconds,
            "stale_timeout_seconds": self._stale_timeout_seconds,
            "stale_scan_interval_seconds": self._stale_scan_interval_seconds,
            "chapter_timeout_seconds": self._chapter_timeout_seconds,
            "blueprint_timeout_seconds": self._blueprint_timeout_seconds,
            "auto_retry_max": self._default_max_retries,
            "retry_backoff_base_seconds": self._retry_backoff_base_seconds,
            "retry_backoff_max_seconds": self._retry_backoff_max_seconds,
            "policy_refresh_interval_seconds": self._policy_refresh_interval_seconds,
        }

    def _runtime_policy_defaults(self) -> Dict[str, int]:
        return {
            "_worker_count": self._clamp_int(settings.generation_task_workers, default=1, min_value=1, max_value=4),
            "_heartbeat_interval_seconds": self._clamp_int(
                settings.generation_task_heartbeat_interval_seconds,
                default=10,
                min_value=3,
                max_value=180,
            ),
            "_stale_timeout_seconds": self._clamp_int(
                settings.generation_task_stale_timeout_seconds,
                default=300,
                min_value=30,
                max_value=3600,
            ),
            "_stale_scan_interval_seconds": self._clamp_int(
                settings.generation_task_stale_scan_interval_seconds,
                default=30,
                min_value=10,
                max_value=600,
            ),
            "_chapter_timeout_seconds": self._clamp_int(
                settings.generation_task_chapter_timeout_seconds,
                default=1800,
                min_value=120,
                max_value=6 * 3600,
            ),
            "_blueprint_timeout_seconds": self._clamp_int(
                settings.generation_task_blueprint_timeout_seconds,
                default=1200,
                min_value=120,
                max_value=6 * 3600,
            ),
            "_default_max_retries": self._clamp_int(
                settings.generation_task_auto_retry_max,
                default=1,
                min_value=0,
                max_value=6,
            ),
            "_retry_backoff_base_seconds": self._clamp_int(
                settings.generation_task_retry_backoff_base_seconds,
                default=8,
                min_value=1,
                max_value=300,
            ),
            "_retry_backoff_max_seconds": self._clamp_int(
                settings.generation_task_retry_backoff_max_seconds,
                default=180,
                min_value=1,
                max_value=3600,
            ),
            "_policy_refresh_interval_seconds": self._clamp_int(
                settings.generation_task_policy_refresh_interval_seconds,
                default=30,
                min_value=5,
                max_value=600,
            ),
        }

    async def _load_runtime_policy_overrides(self) -> Dict[str, str]:
        keys = [key for key, _, _, _ in self._policy_specs()]
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(SystemConfig.key, SystemConfig.value).where(SystemConfig.key.in_(keys))
                )
            ).all()
        return {key: value for key, value in rows if value is not None}

    async def _refresh_runtime_policy(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now < self._next_policy_refresh_at:
            return
        if self._policy_refresh_lock.locked() and not force:
            return

        async with self._policy_refresh_lock:
            now = time.monotonic()
            if not force and now < self._next_policy_refresh_at:
                return

            previous = self._runtime_policy_snapshot()
            defaults = self._runtime_policy_defaults()

            try:
                overrides = await self._load_runtime_policy_overrides()
            except Exception as exc:  # noqa: BLE001
                logger.warning("加载 generation.task 策略失败，继续使用当前配置: error=%s", exc)
                self._next_policy_refresh_at = time.monotonic() + max(5, min(60, self._policy_refresh_interval_seconds))
                return

            for key, attr_name, min_value, max_value in self._policy_specs():
                default = defaults[attr_name]
                raw_value = overrides.get(key)
                parsed_value = (
                    self._clamp_int(raw_value, default=default, min_value=min_value, max_value=max_value)
                    if raw_value is not None
                    else default
                )
                setattr(self, attr_name, parsed_value)

            self._next_policy_refresh_at = time.monotonic() + self._policy_refresh_interval_seconds
            current = self._runtime_policy_snapshot()
            if current == previous:
                return

            if self._running and previous["worker_count"] != current["worker_count"]:
                logger.warning(
                    "generation.task.worker_count 已变更为 %s（当前运行中 worker=%s），重启服务后生效",
                    current["worker_count"],
                    previous["worker_count"],
                )

            logger.info(
                "GenerationTaskRunner policy refreshed: workers=%s heartbeat=%ss stale_timeout=%ss stale_scan=%ss chapter_timeout=%ss blueprint_timeout=%ss auto_retry_max=%s backoff=%s/%ss refresh=%ss",
                current["worker_count"],
                current["heartbeat_interval_seconds"],
                current["stale_timeout_seconds"],
                current["stale_scan_interval_seconds"],
                current["chapter_timeout_seconds"],
                current["blueprint_timeout_seconds"],
                current["auto_retry_max"],
                current["retry_backoff_base_seconds"],
                current["retry_backoff_max_seconds"],
                current["policy_refresh_interval_seconds"],
            )

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return

            await self._refresh_runtime_policy(force=True)
            self._running = True

            async with AsyncSessionLocal() as session:
                service = GenerationTaskService(session)
                recovered = await service.requeue_running_tasks(
                    task_types=[TASK_TYPE_CHAPTER_GENERATION, TASK_TYPE_BLUEPRINT_GENERATION],
                )
                pending = await service.list_pending_tasks(
                    task_types=[TASK_TYPE_CHAPTER_GENERATION, TASK_TYPE_BLUEPRINT_GENERATION],
                    limit=2000,
                )
            for task in pending:
                self.enqueue(task.id)

            for idx in range(self._worker_count):
                worker = asyncio.create_task(self._worker_loop(idx), name=f"generation-task-worker-{idx}")
                self._workers.append(worker)

            self._stale_scan_handle = asyncio.create_task(
                self._stale_recovery_loop(),
                name="generation-task-stale-recovery",
            )

            logger.info(
                "GenerationTaskRunner started: workers=%s recovered=%s pending=%s heartbeat=%ss stale_timeout=%ss chapter_timeout=%ss blueprint_timeout=%ss auto_retry_max=%s backoff=%s/%ss refresh=%ss",
                self._worker_count,
                recovered,
                len(pending),
                self._heartbeat_interval_seconds,
                self._stale_timeout_seconds,
                self._chapter_timeout_seconds,
                self._blueprint_timeout_seconds,
                self._default_max_retries,
                self._retry_backoff_base_seconds,
                self._retry_backoff_max_seconds,
                self._policy_refresh_interval_seconds,
            )

    async def stop(self) -> None:
        async with self._lock:
            if not self._running:
                return
            self._running = False

            if self._stale_scan_handle:
                self._stale_scan_handle.cancel()
                await asyncio.gather(self._stale_scan_handle, return_exceptions=True)
                self._stale_scan_handle = None

            for worker in self._workers:
                worker.cancel()
            await asyncio.gather(*self._workers, return_exceptions=True)
            self._workers.clear()

            running = list(self._running_handles.values())
            for handle in running:
                handle.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            self._running_handles.clear()

            delayed = list(self._delayed_enqueue_handles)
            for handle in delayed:
                handle.cancel()
            await asyncio.gather(*delayed, return_exceptions=True)
            self._delayed_enqueue_handles.clear()
            self._queued_task_ids.clear()

            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                    self._queue.task_done()
                except asyncio.QueueEmpty:
                    break

            logger.info("GenerationTaskRunner stopped")

    def enqueue(self, task_id: str) -> bool:
        if task_id in self._queued_task_ids:
            return False
        self._queued_task_ids.add(task_id)
        self._queue.put_nowait(task_id)
        return True

    async def cancel_running_task(self, task_id: str) -> bool:
        handle = self._running_handles.get(task_id)
        if not handle or handle.done():
            return False
        handle.cancel()
        return True

    def is_running_task(self, task_id: str) -> bool:
        handle = self._running_handles.get(task_id)
        return bool(handle and not handle.done())

    def _task_timeout_seconds(self, task_type: str) -> int:
        if task_type == TASK_TYPE_CHAPTER_GENERATION:
            return self._chapter_timeout_seconds
        if task_type == TASK_TYPE_BLUEPRINT_GENERATION:
            return self._blueprint_timeout_seconds
        return self._chapter_timeout_seconds

    def _retry_backoff_seconds(self, current_retry_count: int) -> int:
        multiplier = 2 ** max(0, int(current_retry_count))
        return max(
            1,
            min(
                self._retry_backoff_max_seconds,
                self._retry_backoff_base_seconds * multiplier,
            ),
        )

    def _schedule_delayed_enqueue(self, task_id: str, delay_seconds: int) -> None:
        async def _enqueue_later() -> None:
            try:
                await asyncio.sleep(max(0, int(delay_seconds)))
                self.enqueue(task_id)
            except asyncio.CancelledError:
                raise
            finally:
                self._delayed_enqueue_handles.discard(handle)

        handle = asyncio.create_task(_enqueue_later(), name=f"generation-task-retry-enqueue-{task_id}")
        self._delayed_enqueue_handles.add(handle)

    async def _worker_loop(self, worker_index: int) -> None:
        while True:
            task_id = await self._queue.get()
            self._queued_task_ids.discard(task_id)

            run_handle = asyncio.create_task(self._execute_task(task_id))
            self._running_handles[task_id] = run_handle
            try:
                await run_handle
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("Worker %s execute task failed: task_id=%s error=%s", worker_index, task_id, exc)
            finally:
                self._running_handles.pop(task_id, None)
                self._queue.task_done()

    async def _execute_task(self, task_id: str) -> None:
        await self._refresh_runtime_policy()

        async with AsyncSessionLocal() as session:
            service = GenerationTaskService(session)
            task = await service.mark_running(
                task_id,
                stage_label="执行中",
                status_message="任务开始执行",
            )
            if not task:
                return

            task_type = task.task_type
            project_id = task.project_id
            chapter_number = task.chapter_number
            user_id = task.user_id
            payload = task.payload if isinstance(task.payload, dict) else {}
            timeout_seconds = self._task_timeout_seconds(task_type)
            trace_context = payload.get("trace_context") if isinstance(payload.get("trace_context"), dict) else {}
            request_id = str(trace_context.get("request_id") or "").strip()
            started_at = task.started_at

        await self._progress(
            task_id,
            max(1, int(getattr(task, "progress_percent", 1) or 1)),
            "执行中",
            "任务开始执行",
            checkpoint={
                "execution_meta": {
                    "request_id": request_id or None,
                    "task_type": task_type,
                    "project_id": project_id,
                    "chapter_number": chapter_number,
                    "worker_started_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

        heartbeat_handle = asyncio.create_task(
            self._heartbeat_loop(task_id),
            name=f"generation-task-heartbeat-{task_id}",
        )
        run_started_perf = time.perf_counter()
        try:
            if task_type == TASK_TYPE_CHAPTER_GENERATION:
                if chapter_number is None:
                    raise ValueError("章节任务缺少 chapter_number")
                chapter_result = await asyncio.wait_for(
                    self._run_chapter_task(
                        task_id=task_id,
                        project_id=project_id,
                        chapter_number=chapter_number,
                        user_id=user_id,
                        payload=payload,
                    ),
                    timeout=timeout_seconds,
                )
                finished_at = datetime.now(timezone.utc)
                try:
                    llm_metrics = await self._collect_task_llm_metrics(
                        project_id=project_id,
                        user_id=user_id,
                        started_at=started_at,
                        finished_at=finished_at,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("统计章节任务 LLM 指标失败: task=%s error=%s", task_id, exc)
                    llm_metrics = {
                        "call_count": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "avg_latency_ms": None,
                        "top_model": None,
                        "top_provider": None,
                    }
                final_result = dict(chapter_result or {})
                final_result["execution"] = {
                    "task_type": task_type,
                    "duration_seconds": round(max(0.0, time.perf_counter() - run_started_perf), 2),
                    "timeout_seconds": timeout_seconds,
                    "request_id": request_id or None,
                    "started_at": started_at.isoformat() if started_at else None,
                    "finished_at": finished_at.isoformat(),
                }
                final_result["llm_metrics"] = llm_metrics
                await self._mark_task_completed(
                    task_id,
                    result=final_result,
                    stage_label="生成完成",
                    status_message=f"第{chapter_number}章生成完成",
                )
                logger.info(
                    "任务执行完成: task_id=%s type=%s project=%s chapter=%s user=%s request_id=%s",
                    task_id,
                    task_type,
                    project_id,
                    chapter_number,
                    user_id,
                    request_id or "-",
                )
                return

            if task_type == TASK_TYPE_BLUEPRINT_GENERATION:
                blueprint_result = await asyncio.wait_for(
                    self._run_blueprint_task(
                        task_id=task_id,
                        project_id=project_id,
                        user_id=user_id,
                    ),
                    timeout=timeout_seconds,
                )
                finished_at = datetime.now(timezone.utc)
                try:
                    llm_metrics = await self._collect_task_llm_metrics(
                        project_id=project_id,
                        user_id=user_id,
                        started_at=started_at,
                        finished_at=finished_at,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("统计蓝图任务 LLM 指标失败: task=%s error=%s", task_id, exc)
                    llm_metrics = {
                        "call_count": 0,
                        "success_count": 0,
                        "error_count": 0,
                        "avg_latency_ms": None,
                        "top_model": None,
                        "top_provider": None,
                    }
                final_result = dict(blueprint_result or {})
                final_result["execution"] = {
                    "task_type": task_type,
                    "duration_seconds": round(max(0.0, time.perf_counter() - run_started_perf), 2),
                    "timeout_seconds": timeout_seconds,
                    "request_id": request_id or None,
                    "started_at": started_at.isoformat() if started_at else None,
                    "finished_at": finished_at.isoformat(),
                }
                final_result["llm_metrics"] = llm_metrics
                await self._mark_task_completed(
                    task_id,
                    result=final_result,
                    stage_label="蓝图完成",
                    status_message="蓝图生成完成",
                )
                logger.info(
                    "任务执行完成: task_id=%s type=%s project=%s user=%s request_id=%s",
                    task_id,
                    task_type,
                    project_id,
                    user_id,
                    request_id or "-",
                )
                return

            await self._mark_task_failed(
                task_id,
                f"未知任务类型: {task_type}",
                stage_label="执行失败",
                status_message="任务执行失败，可重试",
            )
        except asyncio.CancelledError:
            await self._mark_task_canceled(task_id)
            raise
        except asyncio.TimeoutError:
            await self._handle_task_failure(
                task_id,
                error_message=f"任务执行超时（>{timeout_seconds}s）",
                stage_label="执行超时",
                task_type=task_type,
                project_id=project_id,
                chapter_number=chapter_number,
                user_id=user_id,
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001
            await self._handle_task_failure(
                task_id,
                error_message=str(exc),
                stage_label="执行失败",
                task_type=task_type,
                project_id=project_id,
                chapter_number=chapter_number,
                user_id=user_id,
                request_id=request_id,
            )
        finally:
            heartbeat_handle.cancel()
            await asyncio.gather(heartbeat_handle, return_exceptions=True)

    async def _heartbeat_loop(self, task_id: str) -> None:
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval_seconds)
                async with AsyncSessionLocal() as session:
                    service = GenerationTaskService(session)
                    alive = await service.touch_heartbeat(task_id, only_when_running=True)
                if not alive:
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("任务心跳更新失败: task_id=%s error=%s", task_id, exc)

    async def _stale_recovery_loop(self) -> None:
        while True:
            try:
                await self._refresh_runtime_policy()
                await asyncio.sleep(self._stale_scan_interval_seconds)
                await self._recover_stale_running_tasks_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("任务卡死扫描失败: error=%s", exc)

    async def _recover_stale_running_tasks_once(self) -> None:
        running_ids = [task_id for task_id, handle in self._running_handles.items() if not handle.done()]
        async with AsyncSessionLocal() as session:
            service = GenerationTaskService(session)
            recovered_ids = await service.recover_stale_running_tasks(
                stale_seconds=self._stale_timeout_seconds,
                task_types=[TASK_TYPE_CHAPTER_GENERATION, TASK_TYPE_BLUEPRINT_GENERATION],
                exclude_task_ids=running_ids,
                limit=200,
            )
        if not recovered_ids:
            return
        for task_id in recovered_ids:
            self.enqueue(task_id)
        logger.warning(
            "检测到卡死任务并自动恢复: count=%s ids=%s",
            len(recovered_ids),
            ",".join(recovered_ids[:12]),
        )

    async def _prepare_auto_retry(
        self,
        task_id: str,
    ) -> Optional[Tuple[str, int, int, int]]:
        await self._refresh_runtime_policy()

        async with AsyncSessionLocal() as session:
            service = GenerationTaskService(session)
            task = await service.get_task(task_id)
            if not task:
                return None
            if task.task_type not in {TASK_TYPE_CHAPTER_GENERATION, TASK_TYPE_BLUEPRINT_GENERATION}:
                return None
            if task.status == TASK_STATUS_CANCELED:
                return None

            current_retry_count = max(0, int(task.retry_count or 0))
            max_retries = max(0, int(task.max_retries or self._default_max_retries))
            if current_retry_count >= max_retries:
                return None

            payload = dict(task.payload or {}) if isinstance(task.payload, dict) else {}
            if task.task_type == TASK_TYPE_CHAPTER_GENERATION:
                checkpoint = task.checkpoint if isinstance(task.checkpoint, dict) else {}
                variants = checkpoint.get("generated_variants")
                if isinstance(variants, list):
                    resume_variants = [item for item in variants if isinstance(item, dict)]
                    if resume_variants:
                        payload["resume_variants"] = resume_variants

            next_retry_count = current_retry_count + 1
            backoff_seconds = self._retry_backoff_seconds(current_retry_count)
            retry_task = await service.create_task(
                task_type=task.task_type,
                project_id=task.project_id,
                user_id=int(task.user_id),
                chapter_number=task.chapter_number,
                payload=payload,
                retry_count=next_retry_count,
                max_retries=max_retries,
                resume_from_task_id=task.id,
                stage_label="自动重试排队",
                status_message=f"任务失败后自动重试（第{next_retry_count}/{max_retries}次），等待执行",
            )
            return retry_task.id, backoff_seconds, next_retry_count, max_retries

    async def _handle_task_failure(
        self,
        task_id: str,
        *,
        error_message: str,
        stage_label: str = "执行失败",
        task_type: Optional[str] = None,
        project_id: Optional[str] = None,
        chapter_number: Optional[int] = None,
        user_id: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> None:
        failure_category = classify_task_failure(
            error_message,
            status_message=stage_label,
        )
        failure_label = failure_category_label(failure_category)

        async def _notify_failure() -> None:
            if not task_type or not project_id:
                return
            try:
                async with AsyncSessionLocal() as session:
                    alert_service = GenerationAlertService(session)
                    alert_result = await alert_service.notify_task_failure(
                        task_id=task_id,
                        task_type=task_type,
                        project_id=project_id,
                        chapter_number=chapter_number,
                        user_id=user_id,
                        stage_label=stage_label,
                        error_message=error_message,
                        request_id=request_id,
                    )
                if alert_result.get("sent"):
                    logger.warning(
                        "任务失败告警已发送: task_id=%s type=%s project=%s chapter=%s channels=%s",
                        task_id,
                        task_type,
                        project_id,
                        chapter_number,
                        ",".join(alert_result.get("channels") or []),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "任务失败告警发送异常: task_id=%s type=%s project=%s chapter=%s error=%s",
                    task_id,
                    task_type,
                    project_id,
                    chapter_number,
                    exc,
                )

        retry_plan = await self._prepare_auto_retry(task_id)
        if retry_plan:
            retry_task_id, backoff_seconds, retry_attempt, retry_max = retry_plan
            await self._mark_task_failed(
                task_id,
                (error_message or "任务执行失败"),
                stage_label=stage_label,
                status_message=(
                    f"{failure_label}，已自动安排重试（第{retry_attempt}/{retry_max}次），"
                    f"约 {backoff_seconds}s 后重试"
                ),
            )
            self._schedule_delayed_enqueue(retry_task_id, backoff_seconds)
            logger.warning(
                "任务失败自动重试已安排: source_task=%s retry_task=%s type=%s project=%s chapter=%s user=%s request_id=%s category=%s attempt=%s/%s backoff=%ss error=%s",
                task_id,
                retry_task_id,
                task_type or "-",
                project_id or "-",
                chapter_number,
                user_id,
                request_id or "-",
                failure_category,
                retry_attempt,
                retry_max,
                backoff_seconds,
                (error_message or "")[:220],
            )
            await _notify_failure()
            return

        await self._mark_task_failed(
            task_id,
            (error_message or "任务执行失败"),
            stage_label=stage_label,
            status_message=f"{failure_label}，任务执行失败，可重试",
        )
        logger.warning(
            "任务执行失败: task_id=%s type=%s project=%s chapter=%s user=%s request_id=%s category=%s error=%s",
            task_id,
            task_type or "-",
            project_id or "-",
            chapter_number,
            user_id,
            request_id or "-",
            failure_category,
            (error_message or "")[:240],
        )
        await _notify_failure()

    async def _run_chapter_task(
        self,
        *,
        task_id: str,
        project_id: str,
        chapter_number: int,
        user_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        await self._progress(task_id, 6, "准备章节任务", "正在校验章节与配置")
        await self._raise_if_cancel_requested(task_id)

        writing_notes = payload.get("writing_notes")
        flow_config = payload.get("flow_config")
        if not isinstance(flow_config, dict):
            flow_config = {"preset": "basic"}

        resume_variants = payload.get("resume_variants")
        if not isinstance(resume_variants, list):
            resume_variants = []

        async with AsyncSessionLocal() as session:
            novel_service = NovelService(session)
            chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
            chapter.real_summary = None
            chapter.selected_version_id = None
            chapter.status = "generating"
            await session.commit()

            orchestrator = PipelineOrchestrator(session)

            async def on_progress(progress: int, stage: str, message: str) -> None:
                await self._progress(task_id, progress, stage, message)
                await self._raise_if_cancel_requested(task_id)

            async def on_variant_checkpoint(variants: list[dict]) -> None:
                raw_versions = flow_config.get("versions")
                try:
                    expected_versions = int(raw_versions) if raw_versions is not None else (len(variants) or 1)
                except (TypeError, ValueError):
                    expected_versions = len(variants) or 1
                await self._progress(
                    task_id,
                    min(85, 24 + len(variants) * 15),
                    "生成候选版本",
                    f"已完成 {len(variants)} 个候选版本",
                    checkpoint={
                        "generated_variants": variants,
                        "generated_count": len(variants),
                        "version_count": max(1, expected_versions),
                    },
                )
                await self._raise_if_cancel_requested(task_id)

            try:
                result = await orchestrator.generate_chapter(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    writing_notes=writing_notes,
                    user_id=user_id,
                    flow_config=flow_config,
                    progress_callback=on_progress,
                    variant_callback=on_variant_checkpoint,
                    resume_variants=resume_variants,
                )
            except asyncio.CancelledError:
                chapter.status = "failed"
                await session.commit()
                raise
            except Exception:
                chapter.status = "failed"
                await session.commit()
                raise

            try:
                guard_summary = await self._run_consistency_guard(
                    task_id=task_id,
                    session=session,
                    chapter=chapter,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    user_id=user_id,
                    generation_result=result,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "一致性守护执行失败，已降级跳过: project=%s chapter=%s task=%s error=%s",
                    project_id,
                    chapter_number,
                    task_id,
                    exc,
                )
                guard_summary = {
                    "enabled": True,
                    "status": "error",
                    "message": "一致性守护执行失败，已跳过",
                }

        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "best_version_index": result.get("best_version_index", 0),
            "variant_count": len(result.get("variants") or []),
            "consistency_guard": guard_summary,
        }

    async def _run_blueprint_task(
        self,
        *,
        task_id: str,
        project_id: str,
        user_id: int,
    ) -> Dict[str, Any]:
        await self._progress(task_id, 6, "准备蓝图任务", "正在整理对话历史")
        await self._raise_if_cancel_requested(task_id)

        async with AsyncSessionLocal() as session:
            try:
                response = await generate_blueprint_for_project(
                    session,
                    project_id=project_id,
                    user_id=user_id,
                    progress_callback=lambda p, s, m: self._blueprint_progress(task_id, p, s, m),
                )
            except asyncio.CancelledError:
                await self._set_project_blueprint_failed(project_id, user_id)
                raise
            except Exception:
                await self._set_project_blueprint_failed(project_id, user_id)
                raise

        return {
            "project_id": project_id,
            "title": response.blueprint.title,
        }

    async def _run_consistency_guard(
        self,
        *,
        task_id: str,
        session,
        chapter: Chapter,
        project_id: str,
        chapter_number: int,
        user_id: int,
        generation_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        policy = await self._resolve_consistency_guard_policy(session)
        if not policy.enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "一致性守护已关闭",
            }

        variants = generation_result.get("variants")
        if not isinstance(variants, list) or not variants:
            return {
                "enabled": True,
                "status": "skipped",
                "message": "无可检查版本",
            }

        best_index = int(generation_result.get("best_version_index", 0) or 0)
        best_index = max(0, min(best_index, len(variants) - 1))
        best_variant = variants[best_index] if isinstance(variants[best_index], dict) else {}
        chapter_text = str(best_variant.get("content") or "").strip()
        if not chapter_text:
            return {
                "enabled": True,
                "status": "skipped",
                "message": "候选版本内容为空，跳过一致性守护",
            }

        await self._progress(task_id, 92, "一致性守护", "正在检查设定与章节一致性")
        sync_session = getattr(session, "sync_session", session)
        consistency_service = ConsistencyService(sync_session, LLMService(session))
        check_result = await consistency_service.check_consistency(
            project_id=project_id,
            chapter_text=chapter_text,
            user_id=user_id,
            include_foreshadowing=True,
        )
        report = self._format_consistency_report(check_result)
        violations_total = len(report["violations"])
        violations_to_fix = self._filter_guard_violations(
            check_result.violations or [],
            min_severity=policy.min_severity,
            limit=policy.max_violations,
        )

        base_payload = {
            "enabled": True,
            "min_severity": policy.min_severity,
            "auto_fix": policy.auto_fix,
            "auto_select_fixed": policy.auto_select_fixed,
            "violations_total": violations_total,
            "violations_fixable": len(violations_to_fix),
            "is_consistent": bool(report["is_consistent"]),
            "summary": report["summary"],
            "report": report,
        }
        checked_at = datetime.utcnow().isoformat()

        target_version_id = best_variant.get("version_id")
        target_version_pk: Optional[int] = None
        if target_version_id is not None:
            try:
                target_version_pk = int(target_version_id)
            except Exception:
                target_version_pk = None
            if target_version_pk is not None:
                existing_version = await session.get(ChapterVersion, target_version_pk)
                if existing_version:
                    metadata = existing_version.metadata if isinstance(existing_version.metadata, dict) else {}
                    metadata["consistency_guard"] = {
                        "checked_at": checked_at,
                        "report": report,
                    }
                    existing_version.metadata = metadata

        if not violations_to_fix:
            await session.commit()
            return {
                **base_payload,
                "status": "passed" if bool(report["is_consistent"]) else "review_required",
                "message": "一致性守护通过",
            }

        if not policy.auto_fix:
            await session.commit()
            return {
                **base_payload,
                "status": "review_required",
                "message": "检测到冲突，已标记待人工修复",
            }

        await self._progress(task_id, 95, "一致性守护修复", "正在生成一致性修复版本")
        fixed_content = await consistency_service.auto_fix(
            project_id=project_id,
            chapter_text=chapter_text,
            violations=violations_to_fix,
            user_id=user_id,
        )
        normalized_fixed = str(fixed_content or "").strip()
        if not normalized_fixed or normalized_fixed == chapter_text:
            await session.commit()
            return {
                **base_payload,
                "status": "review_required",
                "message": "一致性修复未生成有效差异，建议人工处理",
            }

        fix_label = f"guard-fix-{datetime.utcnow().strftime('%m%d%H%M%S')}"
        fixed_meta = {
            "source": "consistency_guard_auto_fix",
            "fixed_from_version_id": target_version_pk,
            "checked_at": checked_at,
            "min_severity": policy.min_severity,
            "report": report,
        }
        fixed_version = ChapterVersion(
            chapter_id=chapter.id,
            content=normalized_fixed,
            version_label=fix_label,
            metadata=fixed_meta,
        )
        session.add(fixed_version)
        await session.flush()

        auto_selected = False
        if policy.auto_select_fixed:
            chapter.selected_version_id = fixed_version.id
            chapter.status = "successful"
            chapter.word_count = len(normalized_fixed)
            auto_selected = True

        variants.append(
            {
                "index": len(variants),
                "version_id": fixed_version.id,
                "content": normalized_fixed,
                "metadata": fixed_meta,
            }
        )
        if auto_selected:
            generation_result["best_version_index"] = len(variants) - 1

        await session.commit()
        return {
            **base_payload,
            "status": "fixed",
            "message": "已生成一致性修复版本",
            "fixed_version_id": fixed_version.id,
            "auto_selected": auto_selected,
        }

    async def _blueprint_progress(self, task_id: str, progress: int, stage: str, message: str) -> None:
        await self._progress(task_id, progress, stage, message)
        await self._raise_if_cancel_requested(task_id)

    async def _set_project_blueprint_failed(self, project_id: str, user_id: int) -> None:
        async with AsyncSessionLocal() as session:
            service = NovelService(session)
            project = await service.ensure_project_owner(project_id, user_id)
            project.status = "blueprint_failed"
            await session.commit()

    async def _progress(
        self,
        task_id: str,
        progress: int,
        stage: str,
        message: str,
        checkpoint: Optional[Dict[str, Any]] = None,
    ) -> None:
        async with AsyncSessionLocal() as session:
            service = GenerationTaskService(session)
            await service.update_progress(
                task_id,
                progress_percent=progress,
                stage_label=stage,
                status_message=message,
                checkpoint=checkpoint,
            )

    async def _raise_if_cancel_requested(self, task_id: str) -> None:
        async with AsyncSessionLocal() as session:
            service = GenerationTaskService(session)
            if await service.is_cancel_requested(task_id):
                raise asyncio.CancelledError()

    async def _mark_task_completed(
        self,
        task_id: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        stage_label: str = "已完成",
        status_message: str = "任务执行完成",
    ) -> None:
        async with AsyncSessionLocal() as session:
            service = GenerationTaskService(session)
            await service.complete_task(
                task_id,
                result=result,
                stage_label=stage_label,
                status_message=status_message,
            )

    async def _mark_task_failed(
        self,
        task_id: str,
        error_message: str,
        *,
        stage_label: str = "执行失败",
        status_message: str = "任务执行失败，可重试",
    ) -> None:
        async with AsyncSessionLocal() as session:
            task_service = GenerationTaskService(session)
            task = await task_service.get_task(task_id)
            if task and task.task_type == TASK_TYPE_CHAPTER_GENERATION and task.chapter_number is not None:
                chapter = (
                    await session.execute(
                        select(Chapter).where(
                            Chapter.project_id == task.project_id,
                            Chapter.chapter_number == task.chapter_number,
                        )
                    )
                ).scalars().first()
                if chapter:
                    await session.execute(
                        update(Chapter)
                        .where(
                            Chapter.project_id == task.project_id,
                            Chapter.chapter_number == task.chapter_number,
                        )
                        .values(status="failed")
                    )
                    await session.commit()
            await task_service.fail_task(
                task_id,
                error_message=(error_message or "任务执行失败"),
                stage_label=stage_label,
                status_message=status_message,
            )

    async def _mark_task_canceled(self, task_id: str) -> None:
        async with AsyncSessionLocal() as session:
            task_service = GenerationTaskService(session)
            task = await task_service.get_task(task_id)
            if task and task.task_type == TASK_TYPE_CHAPTER_GENERATION and task.chapter_number is not None:
                await session.execute(
                    update(Chapter)
                    .where(
                        Chapter.project_id == task.project_id,
                        Chapter.chapter_number == task.chapter_number,
                    )
                    .values(status="failed")
                )
                await session.commit()

            if task and task.status in {TASK_STATUS_FAILED, TASK_STATUS_CANCELED}:
                return
            await task_service.cancel_task(task_id, error_message="任务已取消")


generation_task_runner = GenerationTaskRunner()
