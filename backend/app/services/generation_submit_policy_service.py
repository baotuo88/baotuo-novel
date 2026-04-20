# AIMETA P=任务提交策略服务_并发与排队限流|R=任务提交前策略检查|NR=不含任务执行|E=GenerationSubmitPolicyService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.generation_task import GenerationTask
from ..models.system_config import SystemConfig
from .generation_task_service import (
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_TYPE_BLUEPRINT_GENERATION,
    TASK_TYPE_CHAPTER_GENERATION,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationSubmitPolicy:
    max_running_per_user: int
    max_running_per_project: int
    max_queued_per_user: int
    max_queued_per_project: int
    max_running_blueprint_per_user: int
    max_running_chapter_per_project: int


@dataclass(frozen=True)
class GenerationSubmitSnapshot:
    running_user: int
    running_project: int
    queued_user: int
    queued_project: int
    running_blueprint_user: int
    running_chapter_project: int


class GenerationSubmitPolicyService:
    _SPECS = {
        "generation.submit.max_running_per_user": ("max_running_per_user", 2, 0, 64),
        "generation.submit.max_running_per_project": ("max_running_per_project", 2, 0, 32),
        "generation.submit.max_queued_per_user": ("max_queued_per_user", 30, 0, 500),
        "generation.submit.max_queued_per_project": ("max_queued_per_project", 20, 0, 300),
        "generation.submit.max_running_blueprint_per_user": ("max_running_blueprint_per_user", 1, 0, 8),
        "generation.submit.max_running_chapter_per_project": ("max_running_chapter_per_project", 1, 0, 8),
    }

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _parse_int(raw: Optional[str], *, default: int, min_value: int, max_value: int) -> int:
        try:
            value = int(str(raw).strip()) if raw is not None else default
        except Exception:
            value = default
        return max(min_value, min(max_value, value))

    async def load_policy(self) -> GenerationSubmitPolicy:
        rows = (
            await self.session.execute(
                select(SystemConfig.key, SystemConfig.value).where(
                    SystemConfig.key.in_(list(self._SPECS.keys()))
                )
            )
        ).all()
        override_map = {str(key): value for key, value in rows}

        values: dict[str, int] = {}
        for key, (attr, default, min_value, max_value) in self._SPECS.items():
            values[attr] = self._parse_int(
                override_map.get(key),
                default=default,
                min_value=min_value,
                max_value=max_value,
            )
        return GenerationSubmitPolicy(**values)

    async def inspect_snapshot(
        self,
        *,
        user_id: int,
        project_id: str,
        exclude_task_ids: Optional[Iterable[str]] = None,
    ) -> GenerationSubmitSnapshot:
        excluded = [str(item) for item in (exclude_task_ids or []) if str(item).strip()]
        base_filters = [GenerationTask.status.in_([TASK_STATUS_RUNNING, TASK_STATUS_QUEUED])]
        if excluded:
            base_filters.append(~GenerationTask.id.in_(excluded))

        stmt = select(
            func.coalesce(
                func.sum(
                    case(
                        (and_(GenerationTask.status == TASK_STATUS_RUNNING, GenerationTask.user_id == int(user_id)), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("running_user"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(GenerationTask.status == TASK_STATUS_RUNNING, GenerationTask.project_id == str(project_id)),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("running_project"),
            func.coalesce(
                func.sum(
                    case(
                        (and_(GenerationTask.status == TASK_STATUS_QUEUED, GenerationTask.user_id == int(user_id)), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("queued_user"),
            func.coalesce(
                func.sum(
                    case(
                        (and_(GenerationTask.status == TASK_STATUS_QUEUED, GenerationTask.project_id == str(project_id)), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("queued_project"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                GenerationTask.status == TASK_STATUS_RUNNING,
                                GenerationTask.user_id == int(user_id),
                                GenerationTask.task_type == TASK_TYPE_BLUEPRINT_GENERATION,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("running_blueprint_user"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                GenerationTask.status == TASK_STATUS_RUNNING,
                                GenerationTask.project_id == str(project_id),
                                GenerationTask.task_type == TASK_TYPE_CHAPTER_GENERATION,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("running_chapter_project"),
        ).where(*base_filters)
        result = (await self.session.execute(stmt)).one()
        return GenerationSubmitSnapshot(
            running_user=int(result.running_user or 0),
            running_project=int(result.running_project or 0),
            queued_user=int(result.queued_user or 0),
            queued_project=int(result.queued_project or 0),
            running_blueprint_user=int(result.running_blueprint_user or 0),
            running_chapter_project=int(result.running_chapter_project or 0),
        )

    async def ensure_submit_allowed(
        self,
        *,
        user_id: int,
        project_id: str,
        task_type: str,
        exclude_task_ids: Optional[Iterable[str]] = None,
    ) -> tuple[GenerationSubmitPolicy, GenerationSubmitSnapshot]:
        policy = await self.load_policy()
        snapshot = await self.inspect_snapshot(
            user_id=user_id,
            project_id=project_id,
            exclude_task_ids=exclude_task_ids,
        )

        def _raise_limit(detail: str, *, limit_key: str) -> None:
            logger.info(
                "generation submit rejected: user=%s project=%s task_type=%s limit=%s detail=%s snapshot=%s policy=%s",
                user_id,
                project_id,
                task_type,
                limit_key,
                detail,
                snapshot,
                policy,
            )
            raise HTTPException(status_code=429, detail=detail)

        if policy.max_running_per_user > 0 and snapshot.running_user >= policy.max_running_per_user:
            _raise_limit(
                f"当前账号运行中任务已达上限（{snapshot.running_user}/{policy.max_running_per_user}），"
                "请等待已有任务完成后再提交",
                limit_key="max_running_per_user",
            )
        if policy.max_running_per_project > 0 and snapshot.running_project >= policy.max_running_per_project:
            _raise_limit(
                f"当前项目运行中任务已达上限（{snapshot.running_project}/{policy.max_running_per_project}），"
                "请等待已有任务完成后再提交",
                limit_key="max_running_per_project",
            )
        if policy.max_queued_per_user > 0 and snapshot.queued_user >= policy.max_queued_per_user:
            _raise_limit(
                f"当前账号排队任务已达上限（{snapshot.queued_user}/{policy.max_queued_per_user}），"
                "请稍后再试",
                limit_key="max_queued_per_user",
            )
        if policy.max_queued_per_project > 0 and snapshot.queued_project >= policy.max_queued_per_project:
            _raise_limit(
                f"当前项目排队任务已达上限（{snapshot.queued_project}/{policy.max_queued_per_project}），"
                "请稍后再试",
                limit_key="max_queued_per_project",
            )
        if (
            task_type == TASK_TYPE_BLUEPRINT_GENERATION
            and policy.max_running_blueprint_per_user > 0
            and snapshot.running_blueprint_user >= policy.max_running_blueprint_per_user
        ):
            _raise_limit(
                "当前账号已有蓝图生成任务正在运行，"
                f"上限为 {policy.max_running_blueprint_per_user}，请等待完成后再提交",
                limit_key="max_running_blueprint_per_user",
            )
        if (
            task_type == TASK_TYPE_CHAPTER_GENERATION
            and policy.max_running_chapter_per_project > 0
            and snapshot.running_chapter_project >= policy.max_running_chapter_per_project
        ):
            _raise_limit(
                "当前项目已有章节生成任务正在运行，"
                f"上限为 {policy.max_running_chapter_per_project}，请等待完成后再提交",
                limit_key="max_running_chapter_per_project",
            )

        return policy, snapshot
