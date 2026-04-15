# AIMETA P=任务队列执行器_持久化任务调度|R=排队执行_重启恢复_取消|NR=不含HTTP接口|E=GenerationTaskRunner|X=job|A=队列执行器|D=asyncio,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from sqlalchemy import select, update

from ..db.session import AsyncSessionLocal
from ..models.novel import Chapter
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

logger = logging.getLogger(__name__)


class GenerationTaskRunner:
    def __init__(self) -> None:
        worker_count_raw = os.getenv("GENERATION_TASK_WORKERS", "1").strip()
        try:
            worker_count = int(worker_count_raw)
        except ValueError:
            worker_count = 1
        self._worker_count = max(1, min(worker_count, 4))
        self._heartbeat_interval_seconds = self._parse_env_int(
            "GENERATION_TASK_HEARTBEAT_INTERVAL_SECONDS",
            default=10,
            min_value=3,
            max_value=180,
        )
        self._stale_timeout_seconds = self._parse_env_int(
            "GENERATION_TASK_STALE_TIMEOUT_SECONDS",
            default=300,
            min_value=30,
            max_value=3600,
        )
        self._stale_scan_interval_seconds = self._parse_env_int(
            "GENERATION_TASK_STALE_SCAN_INTERVAL_SECONDS",
            default=30,
            min_value=10,
            max_value=600,
        )

        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._queued_task_ids: set[str] = set()
        self._workers: list[asyncio.Task] = []
        self._running_handles: dict[str, asyncio.Task] = {}
        self._stale_scan_handle: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _parse_env_int(name: str, *, default: int, min_value: int, max_value: int) -> int:
        raw = os.getenv(name, str(default)).strip()
        try:
            value = int(raw)
        except ValueError:
            value = default
        return max(min_value, min(max_value, value))

    async def start(self) -> None:
        async with self._lock:
            if self._running:
                return
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
                "GenerationTaskRunner started: workers=%s recovered=%s pending=%s heartbeat=%ss stale_timeout=%ss",
                self._worker_count,
                recovered,
                len(pending),
                self._heartbeat_interval_seconds,
                self._stale_timeout_seconds,
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

        heartbeat_handle = asyncio.create_task(
            self._heartbeat_loop(task_id),
            name=f"generation-task-heartbeat-{task_id}",
        )
        try:
            if task_type == TASK_TYPE_CHAPTER_GENERATION:
                if chapter_number is None:
                    raise ValueError("章节任务缺少 chapter_number")
                await self._run_chapter_task(
                    task_id=task_id,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    user_id=user_id,
                    payload=payload,
                )
                return

            if task_type == TASK_TYPE_BLUEPRINT_GENERATION:
                await self._run_blueprint_task(
                    task_id=task_id,
                    project_id=project_id,
                    user_id=user_id,
                )
                return

            await self._mark_task_failed(task_id, f"未知任务类型: {task_type}")
        except asyncio.CancelledError:
            await self._mark_task_canceled(task_id)
            raise
        except Exception as exc:  # noqa: BLE001
            await self._mark_task_failed(task_id, str(exc))
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

    async def _mark_task_failed(self, task_id: str, error_message: str) -> None:
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
                stage_label="执行失败",
                status_message="任务执行失败，可重试",
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
