# AIMETA P=任务服务_生成任务创建查询状态变更|R=章节任务_蓝图任务_取消重试恢复|NR=不含具体生成逻辑|E=GenerationTaskService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.generation_task import GenerationTask

TASK_TYPE_CHAPTER_GENERATION = "chapter_generation"
TASK_TYPE_BLUEPRINT_GENERATION = "blueprint_generation"

TASK_STATUS_QUEUED = "queued"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_CANCELED = "canceled"

ACTIVE_TASK_STATUSES = {TASK_STATUS_QUEUED, TASK_STATUS_RUNNING}
FAILED_TASK_STATUSES = {TASK_STATUS_FAILED, TASK_STATUS_CANCELED}
FINAL_TASK_STATUSES = {TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_CANCELED}


class GenerationTaskService:
    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _normalize_checkpoint(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        return {}

    @staticmethod
    def _touch_stage_timeline(
        checkpoint: Dict[str, Any],
        *,
        stage_label: Optional[str],
        progress_percent: Optional[int],
        now: datetime,
    ) -> None:
        if stage_label is None:
            return
        stage = str(stage_label).strip()
        if not stage:
            return

        timeline_raw = checkpoint.get("stage_timeline")
        timeline: list[Dict[str, Any]] = [
            item for item in timeline_raw
            if isinstance(item, dict) and str(item.get("stage") or "").strip()
        ] if isinstance(timeline_raw, list) else []

        entered_at = now.isoformat()
        progress_value = None if progress_percent is None else max(0, min(100, int(progress_percent)))
        if timeline and str(timeline[-1].get("stage") or "").strip() == stage:
            timeline[-1]["updated_at"] = entered_at
            if progress_value is not None:
                timeline[-1]["progress_percent"] = progress_value
        else:
            timeline.append(
                {
                    "stage": stage,
                    "entered_at": entered_at,
                    "updated_at": entered_at,
                    "progress_percent": progress_value,
                }
            )
        checkpoint["stage_timeline"] = timeline[-80:]

    async def create_task(
        self,
        *,
        task_type: str,
        project_id: str,
        user_id: int,
        chapter_number: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
        max_retries: int = 0,
        resume_from_task_id: Optional[str] = None,
        stage_label: Optional[str] = None,
        status_message: Optional[str] = None,
    ) -> GenerationTask:
        task = GenerationTask(
            id=uuid4().hex,
            task_type=task_type,
            project_id=project_id,
            chapter_number=chapter_number,
            user_id=user_id,
            status=TASK_STATUS_QUEUED,
            progress_percent=0,
            stage_label=(stage_label or "排队中"),
            status_message=(status_message or "任务已加入队列，等待执行"),
            payload=payload or {},
            retry_count=max(0, int(retry_count)),
            max_retries=max(0, int(max_retries)),
            resume_from_task_id=resume_from_task_id,
            cancel_requested=False,
            heartbeat_at=None,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def get_task(self, task_id: str) -> Optional[GenerationTask]:
        return await self.session.get(GenerationTask, task_id)

    async def get_active_task(
        self,
        *,
        project_id: str,
        task_type: str,
        chapter_number: Optional[int] = None,
    ) -> Optional[GenerationTask]:
        stmt = self._base_query(project_id=project_id, task_type=task_type, chapter_number=chapter_number)
        stmt = stmt.where(GenerationTask.status.in_(ACTIVE_TASK_STATUSES)).order_by(GenerationTask.created_at.desc())
        result = await self.session.execute(stmt.limit(1))
        return result.scalars().first()

    async def get_latest_task(
        self,
        *,
        project_id: str,
        task_type: str,
        chapter_number: Optional[int] = None,
        statuses: Optional[Iterable[str]] = None,
    ) -> Optional[GenerationTask]:
        stmt = self._base_query(project_id=project_id, task_type=task_type, chapter_number=chapter_number)
        if statuses:
            stmt = stmt.where(GenerationTask.status.in_(list(statuses)))
        stmt = stmt.order_by(GenerationTask.created_at.desc()).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_recent_tasks(
        self,
        *,
        project_id: str,
        task_type: Optional[str] = None,
        chapter_number: Optional[int] = None,
        limit: int = 200,
    ) -> list[GenerationTask]:
        stmt = select(GenerationTask).where(GenerationTask.project_id == project_id)
        if task_type:
            stmt = stmt.where(GenerationTask.task_type == task_type)
        if chapter_number is not None:
            stmt = stmt.where(GenerationTask.chapter_number == chapter_number)
        stmt = stmt.order_by(GenerationTask.created_at.desc()).limit(max(1, min(limit, 2000)))
        rows = await self.session.execute(stmt)
        return rows.scalars().all()

    async def list_pending_tasks(
        self,
        *,
        task_types: Optional[Iterable[str]] = None,
        limit: int = 500,
    ) -> list[GenerationTask]:
        stmt = select(GenerationTask).where(GenerationTask.status == TASK_STATUS_QUEUED)
        if task_types:
            stmt = stmt.where(GenerationTask.task_type.in_(list(task_types)))
        stmt = stmt.order_by(GenerationTask.created_at.asc()).limit(max(1, min(limit, 3000)))
        rows = await self.session.execute(stmt)
        return rows.scalars().all()

    async def requeue_running_tasks(self, *, task_types: Optional[Iterable[str]] = None) -> int:
        stmt = select(GenerationTask).where(GenerationTask.status == TASK_STATUS_RUNNING)
        if task_types:
            stmt = stmt.where(GenerationTask.task_type.in_(list(task_types)))
        rows = (await self.session.execute(stmt)).scalars().all()
        if not rows:
            return 0

        count = 0
        for task in rows:
            task.status = TASK_STATUS_QUEUED
            task.started_at = None
            task.heartbeat_at = None
            task.finished_at = None
            task.cancel_requested = False
            task.stage_label = "恢复排队"
            task.status_message = "检测到服务重启，任务已恢复到队列"
            count += 1
        await self.session.commit()
        return count

    async def recover_stale_running_tasks(
        self,
        *,
        stale_seconds: int,
        task_types: Optional[Iterable[str]] = None,
        exclude_task_ids: Optional[Iterable[str]] = None,
        limit: int = 300,
    ) -> list[str]:
        timeout = max(1, int(stale_seconds))
        stmt = select(GenerationTask).where(GenerationTask.status == TASK_STATUS_RUNNING)
        if task_types:
            stmt = stmt.where(GenerationTask.task_type.in_(list(task_types)))
        stmt = stmt.order_by(GenerationTask.updated_at.asc()).limit(max(1, min(limit, 3000)))

        rows = (await self.session.execute(stmt)).scalars().all()
        if not rows:
            return []

        excluded = set(exclude_task_ids or [])
        now = datetime.now(timezone.utc)
        stale_cutoff = now - timedelta(seconds=timeout)
        recovered_ids: list[str] = []

        for task in rows:
            if task.id in excluded:
                continue

            heartbeat = task.heartbeat_at or task.updated_at or task.started_at or task.created_at
            if heartbeat is None:
                continue
            if getattr(heartbeat, "tzinfo", None) is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)
            if heartbeat > stale_cutoff:
                continue

            task.status = TASK_STATUS_QUEUED
            task.started_at = None
            task.heartbeat_at = None
            task.finished_at = None
            task.cancel_requested = False
            task.stage_label = "恢复排队"
            task.status_message = "检测到任务心跳超时，已自动恢复到队列"
            recovered_ids.append(task.id)

        if recovered_ids:
            await self.session.commit()
        return recovered_ids

    async def mark_running(
        self,
        task_id: str,
        *,
        stage_label: Optional[str] = None,
        status_message: Optional[str] = None,
    ) -> Optional[GenerationTask]:
        task = await self.get_task(task_id)
        if not task or task.status != TASK_STATUS_QUEUED:
            return None
        task.status = TASK_STATUS_RUNNING
        now = datetime.now(timezone.utc)
        task.started_at = now
        task.heartbeat_at = now
        task.finished_at = None
        task.cancel_requested = False
        if stage_label:
            task.stage_label = stage_label
        if status_message:
            task.status_message = status_message
        if task.progress_percent <= 0:
            task.progress_percent = 1
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def update_progress(
        self,
        task_id: str,
        *,
        progress_percent: Optional[int] = None,
        stage_label: Optional[str] = None,
        status_message: Optional[str] = None,
        checkpoint: Optional[Dict[str, Any]] = None,
    ) -> Optional[GenerationTask]:
        task = await self.get_task(task_id)
        if not task:
            return None
        now = datetime.now(timezone.utc)

        if progress_percent is not None:
            task.progress_percent = max(0, min(100, int(progress_percent)))
        if stage_label is not None:
            task.stage_label = stage_label
        if status_message is not None:
            task.status_message = status_message
        if checkpoint is not None or stage_label is not None:
            current = self._normalize_checkpoint(task.checkpoint)
            if checkpoint is not None:
                current.update(checkpoint)
            self._touch_stage_timeline(
                current,
                stage_label=stage_label,
                progress_percent=progress_percent if progress_percent is not None else task.progress_percent,
                now=now,
            )
            current["last_progress_at"] = now.isoformat()
            current["last_progress_percent"] = int(task.progress_percent or 0)
            task.checkpoint = current
        task.heartbeat_at = now
        await self.session.commit()
        return task

    async def touch_heartbeat(self, task_id: str, *, only_when_running: bool = True) -> bool:
        task = await self.get_task(task_id)
        if not task:
            return False
        if only_when_running and task.status != TASK_STATUS_RUNNING:
            return False
        task.heartbeat_at = datetime.now(timezone.utc)
        await self.session.commit()
        return True

    async def set_checkpoint(
        self,
        task_id: str,
        checkpoint: Dict[str, Any],
    ) -> Optional[GenerationTask]:
        task = await self.get_task(task_id)
        if not task:
            return None
        task.checkpoint = checkpoint
        await self.session.commit()
        return task

    async def complete_task(
        self,
        task_id: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        stage_label: str = "已完成",
        status_message: str = "任务执行完成",
    ) -> Optional[GenerationTask]:
        task = await self.get_task(task_id)
        if not task:
            return None
        task.status = TASK_STATUS_COMPLETED
        task.progress_percent = 100
        task.stage_label = stage_label
        task.status_message = status_message
        task.error_message = None
        task.result = result or {}
        now = datetime.now(timezone.utc)
        task.finished_at = now
        task.heartbeat_at = now
        await self.session.commit()
        return task

    async def fail_task(
        self,
        task_id: str,
        *,
        error_message: str,
        stage_label: str = "执行失败",
        status_message: str = "任务执行失败，可重试",
    ) -> Optional[GenerationTask]:
        task = await self.get_task(task_id)
        if not task:
            return None
        task.status = TASK_STATUS_FAILED
        task.progress_percent = 100
        task.stage_label = stage_label
        task.status_message = status_message
        task.error_message = (error_message or "").strip()[:1000] or "任务失败"
        now = datetime.now(timezone.utc)
        task.finished_at = now
        task.heartbeat_at = now
        await self.session.commit()
        return task

    async def cancel_task(
        self,
        task_id: str,
        *,
        error_message: str = "任务已取消",
        stage_label: str = "已取消",
        status_message: str = "任务已取消",
    ) -> Optional[GenerationTask]:
        task = await self.get_task(task_id)
        if not task:
            return None
        task.status = TASK_STATUS_CANCELED
        task.progress_percent = 100
        task.stage_label = stage_label
        task.status_message = status_message
        task.error_message = error_message
        task.cancel_requested = True
        now = datetime.now(timezone.utc)
        task.finished_at = now
        task.heartbeat_at = now
        await self.session.commit()
        return task

    async def request_cancel(self, task_id: str, *, immediate_if_queued: bool = True) -> Optional[GenerationTask]:
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.status == TASK_STATUS_QUEUED and immediate_if_queued:
            return await self.cancel_task(task_id)

        if task.status in FINAL_TASK_STATUSES:
            return task

        task.cancel_requested = True
        task.status_message = "取消请求已提交，正在停止任务"
        await self.session.commit()
        return task

    async def is_cancel_requested(self, task_id: str) -> bool:
        task = await self.get_task(task_id)
        if not task:
            return False
        return bool(task.cancel_requested)

    def _base_query(
        self,
        *,
        project_id: str,
        task_type: str,
        chapter_number: Optional[int],
    ) -> Select[tuple[GenerationTask]]:
        stmt = select(GenerationTask).where(
            GenerationTask.project_id == project_id,
            GenerationTask.task_type == task_type,
        )
        if chapter_number is None:
            stmt = stmt.where(GenerationTask.chapter_number.is_(None))
        else:
            stmt = stmt.where(GenerationTask.chapter_number == chapter_number)
        return stmt
