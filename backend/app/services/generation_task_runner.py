# AIMETA P=任务队列执行器_持久化任务调度|R=排队执行_重启恢复_取消|NR=不含HTTP接口|E=GenerationTaskRunner|X=job|A=队列执行器|D=asyncio,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select, update

from ..core.config import settings
from ..db.session import AsyncSessionLocal
from ..models.novel import Chapter
from ..models.system_config import SystemConfig
from .blueprint_generation_service import generate_blueprint_for_project
from .generation_task_service import (
    TASK_STATUS_CANCELED,
    TASK_STATUS_FAILED,
    TASK_TYPE_BLUEPRINT_GENERATION,
    TASK_TYPE_CHAPTER_GENERATION,
    GenerationTaskService,
)
from .novel_service import NovelService
from .pipeline_orchestrator import PipelineOrchestrator
from ..utils.task_failure import classify_task_failure, failure_category_label

logger = logging.getLogger(__name__)


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

        heartbeat_handle = asyncio.create_task(
            self._heartbeat_loop(task_id),
            name=f"generation-task-heartbeat-{task_id}",
        )
        try:
            if task_type == TASK_TYPE_CHAPTER_GENERATION:
                if chapter_number is None:
                    raise ValueError("章节任务缺少 chapter_number")
                await asyncio.wait_for(
                    self._run_chapter_task(
                        task_id=task_id,
                        project_id=project_id,
                        chapter_number=chapter_number,
                        user_id=user_id,
                        payload=payload,
                    ),
                    timeout=timeout_seconds,
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
                await asyncio.wait_for(
                    self._run_blueprint_task(
                        task_id=task_id,
                        project_id=project_id,
                        user_id=user_id,
                    ),
                    timeout=timeout_seconds,
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

    async def _run_chapter_task(
        self,
        *,
        task_id: str,
        project_id: str,
        chapter_number: int,
        user_id: int,
        payload: Dict[str, Any],
    ) -> None:
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

        await self._mark_task_completed(
            task_id,
            result={
                "project_id": project_id,
                "chapter_number": chapter_number,
                "best_version_index": result.get("best_version_index", 0),
                "variant_count": len(result.get("variants") or []),
            },
            stage_label="生成完成",
            status_message=f"第{chapter_number}章生成完成",
        )

    async def _run_blueprint_task(
        self,
        *,
        task_id: str,
        project_id: str,
        user_id: int,
    ) -> None:
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

        await self._mark_task_completed(
            task_id,
            result={
                "project_id": project_id,
                "title": response.blueprint.title,
            },
            stage_label="蓝图完成",
            status_message="蓝图生成完成",
        )

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
