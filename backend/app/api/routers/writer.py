# AIMETA P=写作API_章节生成和大纲创建|R=章节生成_大纲生成_评审_L2导演脚本_护栏检查|NR=不含数据存储|E=route:POST_/api/writer/*|X=http|A=生成_评审_过滤|D=fastapi,openai|S=net,db|RD=./README.ai
"""
Writer API Router - 人类化起点长篇写作系统

核心架构：
- L1 Planner：全知规划层（蓝图/大纲）
- L2 Director：章节导演脚本（ChapterMission）
- L3 Writer：有限视角正文生成

关键改进：
1. 信息可见性过滤：L3 Writer 只能看到已登场角色
2. 跨章 1234 逻辑：通过 ChapterMission 控制每章只写一个节拍
3. 后置护栏检查：自动检测并修复违规内容
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...core.config import settings
from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
from ...models.novel import Chapter, ChapterOutline, ChapterVersion
from ...schemas.novel import (
    Chapter as ChapterSchema,
    AdvancedGenerateRequest,
    AdvancedGenerateResponse,
    ChapterGenerationStatus,
    ChapterVersionDiffResponse,
    ChapterVersionListResponse,
    ChapterVersionDetail,
    ChapterVersionRollbackRequest,
    ChapterVersionRollbackResponse,
    DeleteChapterRequest,
    EditChapterRequest,
    EvaluateChapterRequest,
    FinalizeChapterRequest,
    FinalizeChapterResponse,
    GenerateChapterRequest,
    GenerateOutlineRequest,
    NovelProject as NovelProjectSchema,
    SelectVersionRequest,
    UpdateChapterOutlineRequest,
    WriterTaskCenterCancelResponse,
    WriterTaskCenterItem,
    WriterTaskCenterResponse,
    WriterTaskCenterRetryRequest,
    WriterTaskCenterRetryResponse,
)
from ...schemas.prompt import WritingPresetActivateRequest, WritingPresetRead
from ...schemas.user import UserInDB
from ...services.consistency_service import ConsistencyService
from ...services.chapter_context_service import ChapterContextService
from ...services.chapter_ingest_service import ChapterIngestionService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.vector_store_service import VectorStoreService
from ...services.writer_context_builder import WriterContextBuilder
from ...services.chapter_guardrails import ChapterGuardrails
from ...services.ai_review_service import AIReviewService
from ...services.finalize_service import FinalizeService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json
from ...repositories.system_config_repository import SystemConfigRepository
from ...services.pipeline_orchestrator import PipelineOrchestrator

router = APIRouter(prefix="/api/writer", tags=["Writer"])
logger = logging.getLogger(__name__)

_WRITER_ACTIVE_STATUSES = {
    ChapterGenerationStatus.GENERATING.value,
    ChapterGenerationStatus.EVALUATING.value,
    ChapterGenerationStatus.SELECTING.value,
    ChapterGenerationStatus.WAITING_FOR_CONFIRM.value,
}
_WRITER_FAILED_STATUSES = {
    ChapterGenerationStatus.FAILED.value,
    ChapterGenerationStatus.EVALUATION_FAILED.value,
}
_WRITER_DONE_STATUSES = {ChapterGenerationStatus.SUCCESSFUL.value}
_WRITER_TASK_HANDLES: Dict[str, asyncio.Task] = {}
_WRITER_TASK_OWNERS: Dict[str, int] = {}
_WRITER_TASK_ERROR_MESSAGES: Dict[str, str] = {}


def _build_writer_task_id(project_id: str, chapter_number: int) -> str:
    return f"{project_id}:{chapter_number}"


def _format_consistency_report(result: Any) -> Dict[str, Any]:
    return {
        "is_consistent": bool(result.is_consistent),
        "summary": str(result.summary or ""),
        "check_time_ms": int(result.check_time_ms or 0),
        "violations": [
            {
                "severity": v.severity.value if hasattr(v.severity, "value") else str(v.severity),
                "category": v.category,
                "description": v.description,
                "location": v.location,
                "suggested_fix": v.suggested_fix,
                "confidence": v.confidence,
            }
            for v in (result.violations or [])
        ],
    }


def _writer_queue_state(status_value: str) -> Literal["active", "failed", "done", "other"]:
    if status_value in _WRITER_ACTIVE_STATUSES:
        return "active"
    if status_value in _WRITER_FAILED_STATUSES:
        return "failed"
    if status_value in _WRITER_DONE_STATUSES:
        return "done"
    return "other"


def _writer_progress(status_value: str) -> Tuple[int, str, str]:
    if status_value == ChapterGenerationStatus.GENERATING.value:
        return 35, "生成正文", "AI 正在生成章节正文"
    if status_value == ChapterGenerationStatus.EVALUATING.value:
        return 72, "评审版本", "AI 正在评审候选版本"
    if status_value == ChapterGenerationStatus.WAITING_FOR_CONFIRM.value:
        return 88, "等待确认", "候选版本已生成，等待选择"
    if status_value == ChapterGenerationStatus.SELECTING.value:
        return 94, "确认版本", "正在确认最终版本"
    if status_value == ChapterGenerationStatus.SUCCESSFUL.value:
        return 100, "已完成", "章节已完成"
    if status_value == ChapterGenerationStatus.EVALUATION_FAILED.value:
        return 100, "评审失败", "版本评审失败，可重试"
    if status_value == ChapterGenerationStatus.FAILED.value:
        return 100, "生成失败", "章节生成失败，可重试"
    return 0, "未开始", "任务尚未开始"


def _dispatch_writer_generation_task(
    *,
    project_id: str,
    chapter_number: int,
    writing_notes: Optional[str],
    user_id: int,
) -> tuple[str, bool]:
    task_id = _build_writer_task_id(project_id, chapter_number)
    existing = _WRITER_TASK_HANDLES.get(task_id)
    if existing and not existing.done():
        return task_id, False

    task = asyncio.create_task(
        _generate_chapter_pipeline_async(
            project_id=project_id,
            chapter_number=chapter_number,
            writing_notes=writing_notes,
            user_id=user_id,
            task_id=task_id,
        )
    )
    _WRITER_TASK_HANDLES[task_id] = task
    _WRITER_TASK_OWNERS[task_id] = user_id

    def _cleanup(_: asyncio.Task, task_key: str = task_id) -> None:
        current = _WRITER_TASK_HANDLES.get(task_key)
        if current is task:
            _WRITER_TASK_HANDLES.pop(task_key, None)
            _WRITER_TASK_OWNERS.pop(task_key, None)

    task.add_done_callback(_cleanup)
    return task_id, True


async def _load_project_schema(service: NovelService, project_id: str, user_id: int) -> NovelProjectSchema:
    return await service.get_project_schema(project_id, user_id)


def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
    """截取章节结尾文本，默认保留 500 字。"""
    if not text:
        return ""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


def _resolve_stale_generation_seconds() -> int:
    raw = os.getenv("WRITER_GENERATING_STALE_SECONDS", "300").strip()
    try:
        return max(60, int(raw))
    except ValueError:
        return 300


def _compute_age_seconds(ts: Optional[datetime]) -> Optional[float]:
    if not ts:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    else:
        ts = ts.astimezone(timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())


async def _resolve_version_count(session: AsyncSession) -> int:
    """
    解析章节版本数量配置，优先级：
    1) SystemConfig: writer.chapter_versions
    2) SystemConfig: writer.version_count（兼容旧键）
    3) ENV: WRITER_CHAPTER_VERSION_COUNT / WRITER_CHAPTER_VERSIONS（与 config.py 对齐）
    4) ENV: WRITER_VERSION_COUNT（兼容旧）
    5) settings.writer_chapter_versions（默认=2）
    """
    repo = SystemConfigRepository(session)
    # 1) 新键优先，兼容旧键
    for key in ("writer.chapter_versions", "writer.version_count"):
        record = await repo.get_by_key(key)
        if record and record.value:
            try:
                val = int(record.value)
                if val >= 1:
                    return val
            except ValueError:
                pass
    # 2) 环境变量（与 Settings 对齐）
    for env in ("WRITER_CHAPTER_VERSION_COUNT", "WRITER_CHAPTER_VERSIONS", "WRITER_VERSION_COUNT"):
        v = os.getenv(env)
        if v:
            try:
                val = int(v)
                if val >= 1:
                    return val
            except ValueError:
                pass
    # 3) 默认值
    return int(settings.writer_chapter_versions)


@router.get("/presets", response_model=List[WritingPresetRead])
async def list_writing_presets(
    session: AsyncSession = Depends(get_session),
    _: UserInDB = Depends(get_current_user),
) -> List[WritingPresetRead]:
    prompt_service = PromptService(session)
    return await prompt_service.list_writing_presets()


@router.put("/presets/active", response_model=Optional[WritingPresetRead])
async def set_active_writing_preset(
    payload: WritingPresetActivateRequest,
    session: AsyncSession = Depends(get_session),
    _: UserInDB = Depends(get_current_user),
) -> Optional[WritingPresetRead]:
    prompt_service = PromptService(session)
    try:
        return await prompt_service.activate_writing_preset(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


async def _generate_chapter_mission(
    llm_service: LLMService,
    prompt_service: PromptService,
    blueprint_dict: dict,
    previous_summary: str,
    previous_tail: str,
    outline_title: str,
    outline_summary: str,
    writing_notes: str,
    introduced_characters: List[str],
    all_characters: List[str],
    user_id: int,
    project_id: Optional[str] = None,
) -> Optional[dict]:
    """
    L2 Director: 生成章节导演脚本（ChapterMission）
    """
    plan_prompt = await prompt_service.get_prompt("chapter_plan")
    if not plan_prompt:
        logger.warning("未配置 chapter_plan 提示词，跳过导演脚本生成")
        return None

    plan_input = f"""
[上一章摘要]
{previous_summary or "暂无（这是第一章）"}

[上一章结尾]
{previous_tail or "暂无（这是第一章）"}

[当前章节大纲]
标题：{outline_title}
摘要：{outline_summary}

[已登场角色]
{json.dumps(introduced_characters, ensure_ascii=False) if introduced_characters else "暂无"}

[全部角色]
{json.dumps(all_characters, ensure_ascii=False)}

[写作指令]
{writing_notes or "无额外指令"}
"""

    try:
        response = await llm_service.get_llm_response(
            system_prompt=plan_prompt,
            conversation_history=[{"role": "user", "content": plan_input}],
            temperature=0.3,
            user_id=user_id,
            timeout=120.0,
            project_id=project_id,
        )
        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned)
        mission = json.loads(normalized)
        logger.info("成功生成章节导演脚本: macro_beat=%s", mission.get("macro_beat"))
        return mission
    except Exception as exc:
        logger.warning("生成章节导演脚本失败，将使用默认模式: %s", exc)
        return None


async def _rewrite_with_guardrails(
    llm_service: LLMService,
    prompt_service: PromptService,
    original_text: str,
    chapter_mission: Optional[dict],
    violations_text: str,
    user_id: int,
    project_id: Optional[str] = None,
) -> str:
    """
    使用护栏修复提示词重写违规内容
    """
    rewrite_prompt = await prompt_service.get_prompt("rewrite_guardrails")
    if not rewrite_prompt:
        logger.warning("未配置 rewrite_guardrails 提示词，跳过自动修复")
        return original_text

    rewrite_input = f"""
[原文]
{original_text}

[章节导演脚本]
{json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无"}

[违规列表]
{violations_text}
"""

    try:
        response = await llm_service.get_llm_response(
            system_prompt=rewrite_prompt,
            conversation_history=[{"role": "user", "content": rewrite_input}],
            temperature=0.3,
            user_id=user_id,
            timeout=300.0,
            response_format=None,
            project_id=project_id,
        )
        cleaned = remove_think_tags(response)
        logger.info("成功修复违规内容")
        return cleaned
    except Exception as exc:
        logger.warning("自动修复失败，返回原文: %s", exc)
        return original_text


async def _refresh_edit_summary_and_ingest(
    project_id: str,
    chapter_number: int,
    content: str,
    user_id: Optional[int],
) -> None:
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)

        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.selected_version))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if not chapter:
            return

        summary_text = None
        try:
            summary = await llm_service.get_summary(
                content,
                temperature=0.15,
                user_id=user_id,
                project_id=project_id,
            )
            summary_text = remove_think_tags(summary)
        except Exception as exc:
            logger.warning("编辑章节后自动生成摘要失败: %s", exc)

        if summary_text and chapter.selected_version and chapter.selected_version.content == content:
            chapter.real_summary = summary_text
            await session.commit()

        try:
            outline_stmt = select(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number,
            )
            outline_result = await session.execute(outline_stmt)
            outline = outline_result.scalars().first()
            title = outline.title if outline and outline.title else f"第{chapter_number}章"
            ingest_service = ChapterIngestionService(llm_service=llm_service)
            await ingest_service.ingest_chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                title=title,
                content=content,
                summary=None,
                user_id=user_id or 0,
            )
            logger.info("章节 %s 向量化入库成功", chapter_number)
        except Exception as exc:
            logger.error("章节 %s 向量化入库失败: %s", chapter_number, exc)


async def _finalize_chapter_async(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        llm_service = LLMService(session)

        stmt = (
            select(Chapter)
            .options(selectinload(Chapter.versions))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        if not chapter:
            return

        selected_version = next(
            (v for v in chapter.versions if v.id == selected_version_id),
            None,
        )
        if not selected_version or not selected_version.content:
            return

        chapter.selected_version_id = selected_version.id
        chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
        chapter.word_count = len(selected_version.content or "")
        await session.commit()

        vector_store = None
        if settings.vector_store_enabled:
            try:
                vector_store = VectorStoreService()
            except RuntimeError as exc:
                logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

        sync_session = getattr(session, "sync_session", session)
        finalize_service = FinalizeService(sync_session, llm_service, vector_store)
        await finalize_service.finalize_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            chapter_text=selected_version.content,
            user_id=user_id,
            skip_vector_update=skip_vector_update,
        )


async def _schedule_finalize_task(
    project_id: str,
    chapter_number: int,
    selected_version_id: int,
    user_id: int,
    skip_vector_update: bool = False,
) -> None:
    await _finalize_chapter_async(
        project_id=project_id,
        chapter_number=chapter_number,
        selected_version_id=selected_version_id,
        user_id=user_id,
        skip_vector_update=skip_vector_update,
    )


async def _generate_chapter_pipeline_async(
    project_id: str,
    chapter_number: int,
    writing_notes: Optional[str],
    user_id: int,
    task_id: Optional[str] = None,
) -> None:
    task_key = task_id or _build_writer_task_id(project_id, chapter_number)
    _WRITER_TASK_ERROR_MESSAGES.pop(task_key, None)
    async with AsyncSessionLocal() as bg_session:
        orchestrator = PipelineOrchestrator(bg_session)
        novel_service = NovelService(bg_session)
        async_max_seconds_raw = os.getenv("WRITER_ASYNC_MAX_SECONDS", "480").strip()
        async_versions_raw = os.getenv("WRITER_ASYNC_VERSION_COUNT", "").strip()
        try:
            async_max_seconds = max(60, int(async_max_seconds_raw))
        except ValueError:
            async_max_seconds = 480
        # 版本数优先级：
        # 1) WRITER_ASYNC_VERSION_COUNT（仅异步路径专用覆盖）
        # 2) 系统配置 writer.chapter_versions / writer.version_count
        # 3) WRITER_CHAPTER_VERSION_COUNT / settings 默认值
        if async_versions_raw:
            try:
                async_versions = max(1, int(async_versions_raw))
            except ValueError:
                logger.warning(
                    "WRITER_ASYNC_VERSION_COUNT 非法值 %s，回退到通用版本数配置",
                    async_versions_raw,
                )
                async_versions = await _resolve_version_count(bg_session)
        else:
            async_versions = await _resolve_version_count(bg_session)
        try:
            await asyncio.wait_for(
                orchestrator.generate_chapter(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    writing_notes=writing_notes,
                    user_id=user_id,
                    flow_config={
                        "preset": "basic",
                        "versions": async_versions,
                    },
                ),
                timeout=async_max_seconds,
            )
            logger.info(
                "异步章节生成完成: project_id=%s chapter=%s user_id=%s",
                project_id,
                chapter_number,
                user_id,
            )
            _WRITER_TASK_ERROR_MESSAGES.pop(task_key, None)
        except asyncio.TimeoutError:
            logger.error(
                "异步章节生成超时: project_id=%s chapter=%s user_id=%s max_seconds=%s",
                project_id,
                chapter_number,
                user_id,
                async_max_seconds,
            )
            try:
                chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
                chapter.status = ChapterGenerationStatus.FAILED.value
                await bg_session.commit()
                _WRITER_TASK_ERROR_MESSAGES[task_key] = "任务执行超时，请重试（可减少生成版本数）"
            except Exception:
                await bg_session.rollback()
                logger.exception(
                    "异步章节超时后写回状态失败: project_id=%s chapter=%s user_id=%s",
                    project_id,
                    chapter_number,
                    user_id,
                )
                _WRITER_TASK_ERROR_MESSAGES[task_key] = "任务执行超时，且状态写回失败"
        except asyncio.CancelledError:
            logger.info(
                "异步章节生成已取消: project_id=%s chapter=%s user_id=%s",
                project_id,
                chapter_number,
                user_id,
            )
            try:
                chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
                chapter.status = ChapterGenerationStatus.FAILED.value
                await bg_session.commit()
            except Exception:
                await bg_session.rollback()
                logger.exception(
                    "异步章节取消后写回状态失败: project_id=%s chapter=%s user_id=%s",
                    project_id,
                    chapter_number,
                    user_id,
                )
            _WRITER_TASK_ERROR_MESSAGES[task_key] = "任务已取消"
            raise
        except Exception as exc:
            logger.exception(
                "异步章节生成失败: project_id=%s chapter=%s user_id=%s error=%s",
                project_id,
                chapter_number,
                user_id,
                exc,
            )
            try:
                chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
                chapter.status = ChapterGenerationStatus.FAILED.value
                await bg_session.commit()
                _WRITER_TASK_ERROR_MESSAGES[task_key] = f"任务执行异常: {str(exc)[:240]}"
            except Exception:
                await bg_session.rollback()
                logger.exception(
                    "异步章节生成失败后写回状态失败: project_id=%s chapter=%s user_id=%s",
                    project_id,
                    chapter_number,
                    user_id,
                )
                _WRITER_TASK_ERROR_MESSAGES[task_key] = "任务执行异常，且状态写回失败"


@router.post("/advanced/generate", response_model=AdvancedGenerateResponse)
async def advanced_generate_chapter(
    request: AdvancedGenerateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> AdvancedGenerateResponse:
    """
    高级写作入口：通过 PipelineOrchestrator 统一编排生成流程。
    """
    orchestrator = PipelineOrchestrator(session)
    result = await orchestrator.generate_chapter(
        project_id=request.project_id,
        chapter_number=request.chapter_number,
        writing_notes=request.writing_notes,
        user_id=current_user.id,
        flow_config=request.flow_config.model_dump(),
    )

    flow_config = request.flow_config
    if flow_config.async_finalize and result.get("variants"):
        best_index = result.get("best_version_index", 0)
        variants = result["variants"]
        if 0 <= best_index < len(variants):
            selected_version_id = variants[best_index]["version_id"]
            background_tasks.add_task(
                _schedule_finalize_task,
                request.project_id,
                request.chapter_number,
                selected_version_id,
                current_user.id,
                False,
            )

    return AdvancedGenerateResponse(**result)


@router.post("/chapters/{chapter_number}/finalize", response_model=FinalizeChapterResponse)
async def finalize_chapter(
    chapter_number: int,
    request: FinalizeChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> FinalizeChapterResponse:
    """
    定稿入口：选中版本后触发 FinalizeService 进行记忆更新与快照写入。
    """
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(request.project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.versions))
        .where(
            Chapter.project_id == request.project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    selected_version = next(
        (v for v in chapter.versions if v.id == request.selected_version_id),
        None,
    )
    if not selected_version or not selected_version.content:
        raise HTTPException(status_code=400, detail="选中的版本不存在或内容为空")

    chapter.selected_version_id = selected_version.id
    chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
    chapter.word_count = len(selected_version.content or "")
    await session.commit()

    vector_store = None
    if settings.vector_store_enabled and not request.skip_vector_update:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过定稿写入: %s", exc)

    sync_session = getattr(session, "sync_session", session)
    finalize_service = FinalizeService(sync_session, LLMService(session), vector_store)
    finalize_result = await finalize_service.finalize_chapter(
        project_id=request.project_id,
        chapter_number=chapter_number,
        chapter_text=selected_version.content,
        user_id=current_user.id,
        skip_vector_update=request.skip_vector_update or False,
    )

    return FinalizeChapterResponse(
        project_id=request.project_id,
        chapter_number=chapter_number,
        selected_version_id=selected_version.id,
        result=finalize_result,
    )


@router.get("/novels/{project_id}/tasks", response_model=WriterTaskCenterResponse)
async def get_writer_task_center(
    project_id: str,
    limit: int = 80,
    status_group: Literal["active", "failed", "all"] = "all",
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WriterTaskCenterResponse:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1~500 之间")

    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.evaluations))
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.updated_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    if status_group == "active":
        rows = [item for item in rows if (item.status or "").strip() in _WRITER_ACTIVE_STATUSES]
    elif status_group == "failed":
        rows = [item for item in rows if (item.status or "").strip() in _WRITER_FAILED_STATUSES]

    now = datetime.utcnow()
    items: list[WriterTaskCenterItem] = []
    active_count = 0
    failed_count = 0
    done_count = 0

    for chapter in rows:
        status_value = (chapter.status or "not_generated").strip() or "not_generated"
        queue_state = _writer_queue_state(status_value)
        progress_percent, stage_label, status_message = _writer_progress(status_value)
        task_id = _build_writer_task_id(chapter.project_id, chapter.chapter_number)

        if queue_state == "active":
            active_count += 1
        elif queue_state == "failed":
            failed_count += 1
        elif queue_state == "done":
            done_count += 1

        updated_at = chapter.updated_at or chapter.created_at or now
        if getattr(updated_at, "tzinfo", None) is not None:
            updated_at = updated_at.replace(tzinfo=None)
        age_minutes = max(0, int((now - updated_at).total_seconds() // 60))

        task_handle = _WRITER_TASK_HANDLES.get(task_id)
        task_owner_id = _WRITER_TASK_OWNERS.get(task_id)
        can_cancel = bool(
            queue_state == "active"
            and task_handle is not None
            and not task_handle.done()
            and (task_owner_id is None or int(task_owner_id) == int(current_user.id))
        )
        can_retry = queue_state == "failed"

        error_message: Optional[str] = None
        if queue_state == "failed":
            error_message = _WRITER_TASK_ERROR_MESSAGES.get(task_id)
            if not error_message and chapter.evaluations:
                failed_evals = [
                    item for item in chapter.evaluations
                    if ((item.decision or "").strip().lower() == "failed") and item.feedback
                ]
                if failed_evals:
                    latest_failed = sorted(failed_evals, key=lambda item: item.created_at)[-1]
                    error_message = latest_failed.feedback
            if not error_message:
                error_message = "任务失败，请重试。"

        items.append(
            WriterTaskCenterItem(
                task_id=task_id,
                chapter_id=chapter.id,
                project_id=chapter.project_id,
                chapter_number=chapter.chapter_number,
                status=status_value,
                queue_state=queue_state,
                progress_percent=progress_percent,
                stage_label=stage_label,
                status_message=status_message,
                can_cancel=can_cancel,
                can_retry=can_retry,
                word_count=chapter.word_count or 0,
                selected_version_id=chapter.selected_version_id,
                updated_at=updated_at,
                age_minutes=age_minutes,
                error_message=error_message,
            )
        )

    return WriterTaskCenterResponse(
        total=len(items),
        active_count=active_count,
        failed_count=failed_count,
        done_count=done_count,
        items=items,
    )


@router.post("/novels/{project_id}/tasks/{chapter_number}/cancel", response_model=WriterTaskCenterCancelResponse)
async def cancel_writer_task(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WriterTaskCenterCancelResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    stmt = select(Chapter).where(
        Chapter.project_id == project_id,
        Chapter.chapter_number == chapter_number,
    )
    chapter = (await session.execute(stmt)).scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    task_id = _build_writer_task_id(project_id, chapter_number)
    task_handle = _WRITER_TASK_HANDLES.get(task_id)
    if task_handle is None or task_handle.done():
        raise HTTPException(status_code=409, detail="当前任务未在运行中，无法取消")

    task_owner = _WRITER_TASK_OWNERS.get(task_id)
    if task_owner is not None and int(task_owner) != int(current_user.id):
        raise HTTPException(status_code=403, detail="无权取消该任务")

    task_handle.cancel()
    chapter.status = ChapterGenerationStatus.FAILED.value
    await session.commit()
    _WRITER_TASK_ERROR_MESSAGES[task_id] = "任务已取消"

    return WriterTaskCenterCancelResponse(
        accepted=True,
        task_id=task_id,
        project_id=project_id,
        chapter_number=chapter_number,
        message="任务取消请求已提交",
    )


@router.post("/novels/{project_id}/tasks/{chapter_number}/retry", response_model=WriterTaskCenterRetryResponse)
async def retry_writer_task(
    project_id: str,
    chapter_number: int,
    payload: WriterTaskCenterRetryRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WriterTaskCenterRetryResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, chapter_number)
    if not outline:
        raise HTTPException(status_code=400, detail="缺少章节大纲，无法重试生成")

    chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
    previous_status = (chapter.status or "not_generated").strip() or "not_generated"
    task_id = _build_writer_task_id(project_id, chapter_number)
    running_handle = _WRITER_TASK_HANDLES.get(task_id)

    if running_handle and not running_handle.done():
        if not payload.force:
            raise HTTPException(status_code=409, detail="任务正在执行中，若要重试请开启 force")
        running_handle.cancel()
        _WRITER_TASK_HANDLES.pop(task_id, None)
        _WRITER_TASK_OWNERS.pop(task_id, None)

    if previous_status not in _WRITER_FAILED_STATUSES and not payload.force:
        raise HTTPException(status_code=400, detail="当前任务不是失败状态，若要重试请开启 force")

    chapter.real_summary = None
    chapter.selected_version_id = None
    chapter.status = ChapterGenerationStatus.GENERATING.value
    await session.commit()
    _WRITER_TASK_ERROR_MESSAGES.pop(task_id, None)

    new_task_id, dispatched = _dispatch_writer_generation_task(
        project_id=project_id,
        chapter_number=chapter_number,
        writing_notes=payload.writing_notes,
        user_id=current_user.id,
    )

    message = "重试任务已投递" if dispatched else "任务已在执行中，沿用现有任务"
    return WriterTaskCenterRetryResponse(
        accepted=True,
        task_id=new_task_id,
        project_id=project_id,
        chapter_number=chapter_number,
        previous_status=previous_status,
        message=message,
    )


@router.post("/novels/{project_id}/chapters/generate", response_model=NovelProjectSchema)
async def generate_chapter(
    project_id: str,
    request: GenerateChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """
    生成章节正文 - 三层架构流程：
    1. 收集上下文和历史摘要
    2. L2 Director: 生成章节导演脚本（ChapterMission）
    3. 信息可见性过滤：裁剪蓝图，移除未登场角色
    4. L3 Writer: 生成正文（使用 writing_v2 提示词）
    5. 护栏检查：检测并修复违规内容
    """
    force_sync_generation = os.getenv("WRITER_FORCE_SYNC_GENERATION", "").strip().lower() in {"1", "true", "yes", "on"}
    if not force_sync_generation:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)

        outline = await novel_service.get_outline(project_id, request.chapter_number)
        if not outline:
            logger.warning("项目 %s 未找到第 %s 章纲要，异步生成任务未创建", project_id, request.chapter_number)
            raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

        chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
        task_id = _build_writer_task_id(project_id, request.chapter_number)
        running_handle = _WRITER_TASK_HANDLES.get(task_id)
        if chapter.status == ChapterGenerationStatus.GENERATING.value:
            if running_handle and not running_handle.done():
                logger.info(
                    "项目 %s 第 %s 章已在生成中，复用现有异步任务状态 task_id=%s",
                    project_id,
                    request.chapter_number,
                    task_id,
                )
                return await _load_project_schema(novel_service, project_id, current_user.id)
            else:
                stale_seconds = _resolve_stale_generation_seconds()
                age_seconds = _compute_age_seconds(chapter.updated_at or chapter.created_at)
                if age_seconds is not None and age_seconds >= stale_seconds:
                    logger.warning(
                        "检测到疑似卡死生成任务，自动回写失败状态并重新生成: project_id=%s chapter=%s age=%ss threshold=%ss",
                        project_id,
                        request.chapter_number,
                        int(age_seconds),
                        stale_seconds,
                    )
                else:
                    logger.warning(
                        "章节状态为 generating 但未找到运行任务，将自动重新投递: project_id=%s chapter=%s",
                        project_id,
                        request.chapter_number,
                    )
                chapter.status = ChapterGenerationStatus.FAILED.value
                await session.commit()

        chapter.real_summary = None
        chapter.selected_version_id = None
        chapter.status = ChapterGenerationStatus.GENERATING.value
        await session.commit()
        new_task_id, dispatched = _dispatch_writer_generation_task(
            project_id=project_id,
            chapter_number=request.chapter_number,
            writing_notes=request.writing_notes,
            user_id=current_user.id,
        )
        logger.info(
            "项目 %s 第 %s 章异步生成任务已提交，用户 %s，task_id=%s dispatched=%s",
            project_id,
            request.chapter_number,
            current_user.id,
            new_task_id,
            dispatched,
        )
        return await _load_project_schema(novel_service, project_id, current_user.id)

    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)
    context_builder = WriterContextBuilder()
    guardrails = ChapterGuardrails()

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    logger.info("用户 %s 开始为项目 %s 生成第 %s 章", current_user.id, project_id, request.chapter_number)
    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        logger.warning("项目 %s 未找到第 %s 章纲要，生成流程终止", project_id, request.chapter_number)
        raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    chapter.real_summary = None
    chapter.selected_version_id = None
    chapter.status = "generating"
    await session.commit()

    outlines_map = {item.chapter_number: item for item in project.outlines}
    
    # ========== 1. 收集历史上下文 ==========
    completed_chapters = []
    completed_summaries = []
    latest_prev_number = -1
    previous_summary_text = ""
    previous_tail_excerpt = ""
    
    for existing in project.chapters:
        if existing.chapter_number >= request.chapter_number:
            continue
        if existing.selected_version is None or not existing.selected_version.content:
            continue
        if not existing.real_summary:
            summary = await llm_service.get_summary(
                existing.selected_version.content,
                temperature=0.15,
                user_id=current_user.id,
                timeout=180.0,
                project_id=project_id,
            )
            existing.real_summary = remove_think_tags(summary)
            await session.commit()
        completed_chapters.append({
            "chapter_number": existing.chapter_number,
            "title": outlines_map.get(existing.chapter_number).title if outlines_map.get(existing.chapter_number) else f"第{existing.chapter_number}章",
            "summary": existing.real_summary,
        })
        completed_summaries.append(existing.real_summary or "")
        if existing.chapter_number > latest_prev_number:
            latest_prev_number = existing.chapter_number
            previous_summary_text = existing.real_summary or ""
            previous_tail_excerpt = _extract_tail_excerpt(existing.selected_version.content)

    project_schema = await novel_service._serialize_project(project)
    blueprint_dict = project_schema.blueprint.model_dump()

    # 处理关系字段名
    if "relationships" in blueprint_dict and blueprint_dict["relationships"]:
        for relation in blueprint_dict["relationships"]:
            if "character_from" in relation:
                relation["from"] = relation.pop("character_from")
            if "character_to" in relation:
                relation["to"] = relation.pop("character_to")

    outline_title = outline.title or f"第{outline.chapter_number}章"
    outline_summary = outline.summary or "暂无摘要"

    preset_context = await prompt_service.get_active_writing_preset_context()
    raw_writing_notes = (request.writing_notes or "").strip()
    writing_notes_parts: List[str] = []
    preset_notes_prefix = str(preset_context.get("writing_notes_prefix") or "").strip() if preset_context else ""
    if preset_notes_prefix:
        writing_notes_parts.append(preset_notes_prefix)
    if raw_writing_notes:
        writing_notes_parts.append(raw_writing_notes)
    writing_notes = "\n".join(writing_notes_parts) if writing_notes_parts else "无额外写作指令"

    # 提取所有角色名
    all_characters = [c.get("name") for c in blueprint_dict.get("characters", []) if c.get("name")]

    # ========== 2. L2 Director: 生成章节导演脚本 ==========
    chapter_mission = await _generate_chapter_mission(
        llm_service=llm_service,
        prompt_service=prompt_service,
        blueprint_dict=blueprint_dict,
        previous_summary=previous_summary_text,
        previous_tail=previous_tail_excerpt,
        outline_title=outline_title,
        outline_summary=outline_summary,
        writing_notes=writing_notes,
        introduced_characters=[],  # 将在下一步填充
        all_characters=all_characters,
        user_id=current_user.id,
        project_id=project_id,
    )

    # 从导演脚本中提取允许登场的新角色
    allowed_new_characters = []
    if chapter_mission:
        allowed_new_characters = chapter_mission.get("allowed_new_characters", [])

    # ========== 3. 信息可见性过滤 ==========
    visibility_context = context_builder.build_visibility_context(
        blueprint=blueprint_dict,
        completed_summaries=completed_summaries,
        previous_tail=previous_tail_excerpt,
        outline_title=outline_title,
        outline_summary=outline_summary,
        writing_notes=writing_notes,
        allowed_new_characters=allowed_new_characters,
    )

    writer_blueprint = visibility_context["writer_blueprint"]
    forbidden_characters = visibility_context["forbidden_characters"]
    introduced_characters = visibility_context["introduced_characters"]

    logger.info(
        "项目 %s 第 %s 章信息可见性: 已登场=%s, 允许新登场=%s, 禁止=%s",
        project_id,
        request.chapter_number,
        len(introduced_characters),
        len(allowed_new_characters),
        len(forbidden_characters),
    )

    # ========== 4. 准备 RAG 上下文 ==========
    vector_store: Optional[VectorStoreService]
    if not settings.vector_store_enabled:
        vector_store = None
    else:
        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，RAG 检索被禁用: %s", exc)
            vector_store = None
    context_service = ChapterContextService(llm_service=llm_service, vector_store=vector_store)

    query_parts = [outline_title, outline_summary]
    if request.writing_notes:
        query_parts.append(request.writing_notes)
    rag_query = "\n".join(part for part in query_parts if part)
    rag_context = await context_service.retrieve_for_generation(
        project_id=project_id,
        query_text=rag_query or outline.title or outline.summary or "",
        user_id=current_user.id,
    )
    rag_chunks_text = "\n\n".join(rag_context.chunk_texts()) if rag_context.chunks else "未检索到章节片段"
    rag_summaries_text = "\n".join(rag_context.summary_lines()) if rag_context.summaries else "未检索到章节摘要"

    # ========== 5. 构建写作提示词 ==========
    preferred_prompt_name = str(preset_context.get("prompt_name") or "writing_v2").strip() if preset_context else "writing_v2"
    writer_prompt = await prompt_service.get_prompt(preferred_prompt_name)
    if not writer_prompt and preferred_prompt_name != "writing_v2":
        writer_prompt = await prompt_service.get_prompt("writing_v2")
    if not writer_prompt:
        writer_prompt = await prompt_service.get_prompt("writing")
    if not writer_prompt:
        logger.error("未配置写作提示词，无法生成章节内容")
        raise HTTPException(status_code=500, detail="缺少写作提示词，请联系管理员配置")

    generation_temperature = float(preset_context.get("temperature")) if preset_context else 0.9
    generation_top_p = float(preset_context["top_p"]) if preset_context and preset_context.get("top_p") is not None else None
    generation_max_tokens = (
        int(preset_context["max_tokens"]) if preset_context and preset_context.get("max_tokens") is not None else None
    )
    preset_style_rules_text = str(preset_context.get("style_rules_text") or "").strip() if preset_context else ""
    if preset_context:
        logger.info(
            "项目 %s 第 %s 章启用写作预设: preset_id=%s prompt=%s temperature=%.2f top_p=%s max_tokens=%s",
            project_id,
            request.chapter_number,
            preset_context.get("preset_id"),
            preferred_prompt_name,
            generation_temperature,
            generation_top_p,
            generation_max_tokens,
        )

    # 使用裁剪后的蓝图（移除了 full_synopsis 和未登场角色）
    blueprint_text = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)
    
    # 构建导演脚本文本
    mission_text = json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无导演脚本"
    
    # 构建禁止角色列表
    forbidden_text = json.dumps(forbidden_characters, ensure_ascii=False) if forbidden_characters else "无"

    prompt_sections = [
        ("[世界蓝图](JSON，已裁剪)", blueprint_text),
        ("[上一章摘要]", previous_summary_text or "暂无（这是第一章）"),
        ("[上一章结尾]", previous_tail_excerpt or "暂无（这是第一章）"),
        ("[章节导演脚本](JSON)", mission_text),
        ("[检索到的剧情上下文](Markdown)", rag_chunks_text),
        ("[检索到的章节摘要](Markdown)", rag_summaries_text),
        ("[写作Preset风格规则](严格遵循)", preset_style_rules_text),
        ("[当前章节目标]", f"标题：{outline_title}\n摘要：{outline_summary}\n写作要求：{writing_notes}"),
        ("[禁止角色](本章不允许提及)", forbidden_text),
    ]
    prompt_input = "\n\n".join(f"{title}\n{content}" for title, content in prompt_sections if content)
    logger.debug("章节写作提示词长度: %s 字符", len(prompt_input))

    # ========== 6. L3 Writer: 生成正文 ==========
    async def _generate_single_version(idx: int, version_style_hint: Optional[str] = None) -> Dict:
        """生成单个版本，支持差异化风格提示"""
        try:
            # 如果有版本风格提示，添加到 prompt_input
            final_prompt_input = prompt_input
            if version_style_hint:
                final_prompt_input += f"\n\n[版本风格提示]\n{version_style_hint}"

            response = await llm_service.get_llm_response(
                system_prompt=writer_prompt,
                conversation_history=[{"role": "user", "content": final_prompt_input}],
                temperature=generation_temperature,
                user_id=current_user.id,
                timeout=600.0,
                response_format=None,
                max_tokens=generation_max_tokens,
                top_p=generation_top_p,
                project_id=project_id,
            )
            cleaned = remove_think_tags(response)
            normalized = unwrap_markdown_json(cleaned)
            
            # ========== 7. 护栏检查 ==========
            guardrail_result = guardrails.check(
                generated_text=normalized,
                forbidden_characters=forbidden_characters,
                allowed_new_characters=allowed_new_characters,
                pov=chapter_mission.get("pov") if chapter_mission else None,
            )

            final_content = normalized
            guardrail_metadata = {"passed": guardrail_result.passed, "violations": []}

            if not guardrail_result.passed:
                logger.warning(
                    "项目 %s 第 %s 章版本 %s 检测到 %s 个违规",
                    project_id,
                    request.chapter_number,
                    idx + 1,
                    len(guardrail_result.violations),
                )
                guardrail_metadata["violations"] = [
                    {"type": v.type, "severity": v.severity, "description": v.description}
                    for v in guardrail_result.violations
                ]

                # 尝试自动修复
                violations_text = guardrails.format_violations_for_rewrite(guardrail_result)
                final_content = await _rewrite_with_guardrails(
                    llm_service=llm_service,
                    prompt_service=prompt_service,
                    original_text=normalized,
                    chapter_mission=chapter_mission,
                    violations_text=violations_text,
                    user_id=current_user.id,
                    project_id=project_id,
                )

            def _extract_text(value: object) -> Optional[str]:
                if not value:
                    return None
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    for key in ("content", "chapter_content", "chapter_text", "text", "body", "story"):
                        if value.get(key):
                            nested = _extract_text(value.get(key))
                            if nested:
                                return nested
                    return None
                if isinstance(value, list):
                    for item in value:
                        nested = _extract_text(item)
                        if nested:
                            return nested
                return None

            parsed_json = None
            extracted_text = None
            try:
                parsed_json = json.loads(final_content)
                extracted_text = _extract_text(parsed_json)
            except Exception:
                parsed_json = None

            return {
                "content": extracted_text or final_content,
                "parsed_json": parsed_json,
                "guardrail": guardrail_metadata,
                "chapter_mission": chapter_mission,
                "writing_preset": (
                    {
                        "preset_id": preset_context.get("preset_id"),
                        "preset_name": preset_context.get("preset_name"),
                        "prompt_name": preferred_prompt_name,
                        "temperature": generation_temperature,
                        "top_p": generation_top_p,
                        "max_tokens": generation_max_tokens,
                    }
                    if preset_context
                    else None
                ),
            }
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "项目 %s 生成第 %s 章第 %s 个版本时发生异常: %s",
                project_id,
                request.chapter_number,
                idx + 1,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"生成章节第 {idx + 1} 个版本时失败: {str(exc)[:200]}"
            )

    version_count = await _resolve_version_count(session)
    logger.info(
        "项目 %s 第 %s 章计划生成 %s 个版本",
        project_id,
        request.chapter_number,
        version_count,
    )

    # 版本差异化风格提示
    version_style_hints = [
        "情绪更细腻，节奏更慢，多写内心戏和感官描写",
        "冲突更强，节奏更快，多写动作和对话",
        "悬念更重，多埋伏笔，结尾钩子更强",
    ]

    raw_versions = []
    try:
        for idx in range(version_count):
            style_hint = version_style_hints[idx] if idx < len(version_style_hints) else None
            raw_versions.append(await _generate_single_version(idx, style_hint))
    except Exception as exc:
        logger.exception("项目 %s 生成第 %s 章时发生异常: %s", project_id, request.chapter_number, exc)
        chapter.status = "failed"
        await session.commit()
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(
            status_code=500,
            detail=f"生成章节失败: {str(exc)[:200]}"
        )

    contents: List[str] = []
    metadata: List[Dict] = []
    for variant in raw_versions:
        if isinstance(variant, dict):
            if "content" in variant and isinstance(variant["content"], str):
                contents.append(variant["content"])
            elif "chapter_content" in variant:
                contents.append(str(variant["chapter_content"]))
            else:
                contents.append(json.dumps(variant, ensure_ascii=False))
            metadata.append(variant)
        else:
            contents.append(str(variant))
            metadata.append({"raw": variant})

    # ========== 8. AI Review: 自动评审多版本 ==========
    ai_review_result = None
    if len(contents) > 1:
        try:
            ai_review_service = AIReviewService(llm_service, prompt_service)
            ai_review_result = await ai_review_service.review_versions(
                versions=contents,
                chapter_mission=chapter_mission,
                user_id=current_user.id,
            )
            if ai_review_result:
                logger.info(
                    "项目 %s 第 %s 章 AI 评审完成: 推荐版本=%s",
                    project_id,
                    request.chapter_number,
                    ai_review_result.best_version_index,
                )
                # 将评审结果附加到 metadata
                for i, m in enumerate(metadata):
                    m["ai_review"] = {
                        "is_best": i == ai_review_result.best_version_index,
                        "scores": ai_review_result.scores,
                        "evaluation": ai_review_result.overall_evaluation if i == ai_review_result.best_version_index else None,
                        "flaws": ai_review_result.critical_flaws if i == ai_review_result.best_version_index else None,
                        "suggestions": ai_review_result.refinement_suggestions if i == ai_review_result.best_version_index else None,
                    }
        except Exception as exc:
            logger.warning("AI 评审失败，跳过: %s", exc)

    await novel_service.replace_chapter_versions(chapter, contents, metadata)
    logger.info(
        "项目 %s 第 %s 章生成完成，已写入 %s 个版本",
        project_id,
        request.chapter_number,
        len(contents),
    )
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/{chapter_number}/consistency-check")
async def check_chapter_consistency(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(
            selectinload(Chapter.versions),
            selectinload(Chapter.selected_version),
        )
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    chapter = (await session.execute(stmt)).scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    selected_version = chapter.selected_version
    if not selected_version and chapter.versions:
        selected_version = sorted(
            chapter.versions,
            key=lambda item: item.created_at.timestamp() if item.created_at else 0.0,
        )[-1]

    chapter_text = ""
    if selected_version and selected_version.content:
        chapter_text = selected_version.content
    elif chapter.content:
        chapter_text = chapter.content

    if not chapter_text.strip():
        raise HTTPException(status_code=400, detail="章节内容为空，无法执行一致性检查")

    sync_session = getattr(session, "sync_session", session)
    consistency_service = ConsistencyService(sync_session, LLMService(session))
    result = await consistency_service.check_consistency(
        project_id=project_id,
        chapter_text=chapter_text,
        user_id=current_user.id,
        include_foreshadowing=True,
    )
    report = _format_consistency_report(result)

    if selected_version:
        meta = selected_version.metadata if isinstance(selected_version.metadata, dict) else {}
        meta["consistency_report"] = report
        meta["consistency_checked_at"] = datetime.utcnow().isoformat()
        selected_version.metadata = meta
        await session.commit()

    return {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "review": report,
    }


@router.post("/novels/{project_id}/chapters/select", response_model=NovelProjectSchema)
async def select_chapter_version(
    project_id: str,
    request: SelectVersionRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    # 使用 novel_service.select_chapter_version 确保排序一致
    # 该函数会按 created_at 排序并校验索引
    selected_version = await novel_service.select_chapter_version(chapter, request.version_index)
    
    # 校验内容是否为空
    if not selected_version.content or len(selected_version.content.strip()) == 0:
        # 回滚状态，不标记为 successful
        await session.rollback()
        raise HTTPException(status_code=400, detail="选中的版本内容为空，无法确认为最终版")

    # 异步触发向量化入库
    try:
        llm_service = LLMService(session)
        ingest_service = ChapterIngestionService(llm_service=llm_service)
        await ingest_service.ingest_chapter(
            project_id=project_id,
            chapter_number=request.chapter_number,
            title=chapter.title or f"第{request.chapter_number}章",
            content=selected_version.content,
            summary=None
        )
        logger.info(f"章节 {request.chapter_number} 向量化入库成功")
    except Exception as e:
        logger.error(f"章节 {request.chapter_number} 向量化入库失败: {e}")
        # 向量化失败不应阻止版本选择，仅记录错误

    # 选中版本后执行一次自动一致性检查，并写入版本元数据（失败不阻断主流程）
    try:
        sync_session = getattr(session, "sync_session", session)
        consistency_service = ConsistencyService(sync_session, LLMService(session))
        consistency_result = await consistency_service.check_consistency(
            project_id=project_id,
            chapter_text=selected_version.content,
            user_id=current_user.id,
            include_foreshadowing=True,
        )
        metadata = selected_version.metadata if isinstance(selected_version.metadata, dict) else {}
        metadata["consistency_report"] = _format_consistency_report(consistency_result)
        metadata["consistency_checked_at"] = datetime.utcnow().isoformat()
        selected_version.metadata = metadata
        await session.commit()
    except Exception as exc:
        logger.warning(
            "项目 %s 第 %s 章自动一致性检查失败（不影响确认流程）: %s",
            project_id,
            request.chapter_number,
            exc,
        )

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.get(
    "/novels/{project_id}/chapters/{chapter_number}/versions",
    response_model=ChapterVersionListResponse,
)
async def list_chapter_versions(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterVersionListResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.versions))
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    chapter = (await session.execute(stmt)).scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    versions = sorted(chapter.versions or [], key=lambda item: item.created_at, reverse=True)
    now = datetime.utcnow()
    items = [
        ChapterVersionDetail(
            id=item.id,
            version_label=item.version_label,
            created_at=item.created_at or now,
            content=item.content,
            metadata=item.metadata if isinstance(item.metadata, dict) else None,
            word_count=len(item.content or ""),
            is_selected=(chapter.selected_version_id == item.id),
        )
        for item in versions
    ]

    return ChapterVersionListResponse(
        project_id=project_id,
        chapter_number=chapter_number,
        selected_version_id=chapter.selected_version_id,
        total_versions=len(items),
        versions=items,
    )


@router.get(
    "/novels/{project_id}/chapters/{chapter_number}/versions/diff",
    response_model=ChapterVersionDiffResponse,
)
async def get_chapter_version_diff(
    project_id: str,
    chapter_number: int,
    base_version_id: int,
    compare_version_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterVersionDiffResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.versions))
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    chapter = (await session.execute(stmt)).scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    versions_map = {item.id: item for item in (chapter.versions or [])}
    base_version = versions_map.get(base_version_id)
    compare_version = versions_map.get(compare_version_id)
    if not base_version or not compare_version:
        raise HTTPException(status_code=404, detail="版本不存在")

    return ChapterVersionDiffResponse(
        project_id=project_id,
        chapter_number=chapter_number,
        base_version_id=base_version.id,
        compare_version_id=compare_version.id,
        base_version_label=base_version.version_label,
        compare_version_label=compare_version.version_label,
        base_content=base_version.content,
        compare_content=compare_version.content,
    )


@router.post(
    "/novels/{project_id}/chapters/{chapter_number}/versions/rollback",
    response_model=ChapterVersionRollbackResponse,
)
async def rollback_chapter_version(
    project_id: str,
    chapter_number: int,
    payload: ChapterVersionRollbackRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterVersionRollbackResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    stmt = (
        select(Chapter)
        .options(
            selectinload(Chapter.versions),
            selectinload(Chapter.selected_version),
        )
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
        )
    )
    chapter = (await session.execute(stmt)).scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    versions_map = {item.id: item for item in (chapter.versions or [])}
    target_version = versions_map.get(payload.version_id)
    if not target_version:
        raise HTTPException(status_code=404, detail="目标版本不存在")

    selected_before = chapter.selected_version
    if selected_before and selected_before.id == target_version.id:
        raise HTTPException(status_code=400, detail="当前已是该版本，无需回滚")

    timestamp = datetime.utcnow().strftime("%m%d%H%M%S")
    if selected_before and selected_before.content:
        session.add(
            ChapterVersion(
                chapter_id=chapter.id,
                content=selected_before.content,
                version_label=f"snapshot-{timestamp}",
                metadata={
                    "source": "rollback_snapshot",
                    "from_version_id": selected_before.id,
                    "to_version_id": target_version.id,
                },
            )
        )

    restored_version = ChapterVersion(
        chapter_id=chapter.id,
        content=target_version.content,
        version_label=f"rollback-{target_version.id}-{timestamp}",
        metadata={
            "source": "rollback",
            "from_version_id": selected_before.id if selected_before else None,
            "to_version_id": target_version.id,
            "reason": (payload.reason or "").strip() or "manual",
        },
    )
    session.add(restored_version)
    await session.flush()

    chapter.selected_version_id = restored_version.id
    chapter.status = ChapterGenerationStatus.SUCCESSFUL.value
    chapter.word_count = len(restored_version.content or "")
    await session.commit()

    task_id = _build_writer_task_id(project_id, chapter_number)
    _WRITER_TASK_ERROR_MESSAGES.pop(task_id, None)

    return ChapterVersionRollbackResponse(
        project_id=project_id,
        chapter_number=chapter_number,
        selected_version_id=restored_version.id,
        rollback_from_version_id=selected_before.id if selected_before else None,
        rollback_to_version_id=target_version.id,
        message="已回滚到目标版本，并生成回滚快照",
    )


@router.post("/novels/{project_id}/chapters/evaluate", response_model=NovelProjectSchema)
async def evaluate_chapter(
    project_id: str,
    request: EvaluateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    # 确保预加载 selected_version 关系
    from sqlalchemy.orm import selectinload
    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.selected_version))
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    
    if not chapter:
        chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    # 如果没有选中版本，使用最新版本进行评审
    version_to_evaluate = chapter.selected_version
    if not version_to_evaluate:
        # 获取该章节的所有版本，选择最新的一个
        from sqlalchemy.orm import selectinload
        stmt_versions = (
            select(Chapter)
            .options(selectinload(Chapter.versions))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == request.chapter_number,
            )
        )
        result_versions = await session.execute(stmt_versions)
        chapter_with_versions = result_versions.scalars().first()
        
        if not chapter_with_versions or not chapter_with_versions.versions:
            raise HTTPException(status_code=400, detail="该章节还没有生成任何版本，无法进行评审")
        
        # 使用最新的版本（列表中的最后一个）
        version_to_evaluate = chapter_with_versions.versions[-1]
    
    if not version_to_evaluate or not version_to_evaluate.content:
        raise HTTPException(status_code=400, detail="版本内容为空，无法进行评审")

    chapter.status = "evaluating"
    await session.commit()

    eval_prompt = await prompt_service.get_prompt("evaluation")
    if not eval_prompt:
        logger.warning("未配置名为 'evaluation' 的评审提示词，将跳过 AI 评审")
        # 使用 add_chapter_evaluation 创建评审记录
        await novel_service.add_chapter_evaluation(
            chapter=chapter,
            version=version_to_evaluate,
            feedback="未配置评审提示词",
            decision="skipped"
        )
        return await _load_project_schema(novel_service, project_id, current_user.id)

    try:
        evaluation_raw = await llm_service.get_llm_response(
            system_prompt=eval_prompt,
            conversation_history=[{"role": "user", "content": version_to_evaluate.content}],
            temperature=0.3,
            user_id=current_user.id,
            project_id=project_id,
        )
        evaluation_text = remove_think_tags(evaluation_raw)
        
        # 校验 AI 返回的内容不为空
        if not evaluation_text or len(evaluation_text.strip()) == 0:
            raise ValueError("评审结果为空")
        
        # 使用 add_chapter_evaluation 创建评审记录
        # 这会自动设置状态为 WAITING_FOR_CONFIRM
        await novel_service.add_chapter_evaluation(
            chapter=chapter,
            version=version_to_evaluate,
            feedback=evaluation_text,
            decision="reviewed"
        )
        logger.info("项目 %s 第 %s 章评审成功", project_id, request.chapter_number)
    except Exception as exc:
        logger.exception("项目 %s 第 %s 章评审失败: %s", project_id, request.chapter_number, exc)
        # 回滚事务，恢复状态
        await session.rollback()
        
        # 重新加载 chapter 对象（因为 rollback 后对象已脱离 session）
        stmt = (
            select(Chapter)
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == request.chapter_number,
            )
        )
        result = await session.execute(stmt)
        chapter = result.scalars().first()
        
        if chapter:
            # 使用 add_chapter_evaluation 创建失败记录
            # 注意：这里不能再用 add_chapter_evaluation，因为它会设置状态为 waiting_for_confirm
            # 失败时应该设置为 evaluation_failed
            from app.models.novel import ChapterEvaluation
            evaluation_record = ChapterEvaluation(
                chapter_id=chapter.id,
                version_id=version_to_evaluate.id,
                decision="failed",
                feedback=f"评审失败: {str(exc)}",
                score=None
            )
            session.add(evaluation_record)
            chapter.status = "evaluation_failed"
            await session.commit()
        
        # 抛出异常，让前端知道评审失败
        raise HTTPException(status_code=500, detail=f"评审失败: {str(exc)}")
    
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/update-outline", response_model=NovelProjectSchema)
async def update_chapter_outline(
    project_id: str,
    request: UpdateChapterOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="未找到对应章节大纲")

    outline.title = request.title
    outline.summary = request.summary
    await session.commit()

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/delete", response_model=NovelProjectSchema)
async def delete_chapters(
    project_id: str,
    request: DeleteChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    for ch_num in request.chapter_numbers:
        await novel_service.delete_chapter(project_id, ch_num)

    await session.commit()
    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/outline", response_model=NovelProjectSchema)
async def generate_chapters_outline(
    project_id: str,
    request: GenerateOutlineRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    
    # 获取蓝图信息
    project_schema = await novel_service._serialize_project(project)
    blueprint_text = json.dumps(project_schema.blueprint.model_dump(), ensure_ascii=False, indent=2)
    
    # 获取已有的章节大纲
    existing_outlines = [
        f"第{o.chapter_number}章 - {o.title}: {o.summary}"
        for o in sorted(project.outlines, key=lambda x: x.chapter_number)
    ]
    existing_outlines_text = "\n".join(existing_outlines) if existing_outlines else "暂无"

    outline_prompt = await prompt_service.get_prompt("outline_generation")
    if not outline_prompt:
        raise HTTPException(status_code=500, detail="未配置大纲生成提示词")

    prompt_input = f"""
[世界蓝图]
{blueprint_text}

[已有章节大纲]
{existing_outlines_text}

[生成任务]
请从第 {request.start_chapter} 章开始，续写接下来的 {request.num_chapters} 章的大纲。
要求返回 JSON 格式，包含一个 chapters 数组，每个元素包含 chapter_number, title, summary。
"""

    response = await llm_service.get_llm_response(
        system_prompt=outline_prompt,
        conversation_history=[{"role": "user", "content": prompt_input}],
        temperature=0.7,
        user_id=current_user.id,
        project_id=project_id,
    )
    
    cleaned = remove_think_tags(response)
    normalized = unwrap_markdown_json(cleaned)
    try:
        data = json.loads(normalized)
        new_outlines = data.get("chapters", [])
        for item in new_outlines:
            await novel_service.update_or_create_outline(
                project_id, 
                item["chapter_number"], 
                item["title"], 
                item["summary"]
            )
        await session.commit()
    except Exception as exc:
        logger.exception("生成大纲解析失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"大纲生成失败: {str(exc)}")

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit", response_model=NovelProjectSchema)
async def edit_chapter_content(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    
    await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    manual_version = ChapterVersion(
        chapter_id=chapter.id,
        content=request.content,
        version_label=f"manual-edit-{datetime.utcnow().strftime('%m%d%H%M%S')}",
        metadata={
            "source": "manual_edit",
            "from_version_id": chapter.selected_version_id,
        },
    )
    session.add(manual_version)
    await session.flush()
    chapter.selected_version_id = manual_version.id
    
    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    return await _load_project_schema(novel_service, project_id, current_user.id)


@router.post("/novels/{project_id}/chapters/edit-fast", response_model=ChapterSchema)
async def edit_chapter_content_fast(
    project_id: str,
    request: EditChapterRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)

    await novel_service.ensure_project_owner(project_id, current_user.id)
    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)

    manual_version = ChapterVersion(
        chapter_id=chapter.id,
        content=request.content,
        version_label=f"manual-edit-{datetime.utcnow().strftime('%m%d%H%M%S')}",
        metadata={
            "source": "manual_edit",
            "from_version_id": chapter.selected_version_id,
        },
    )
    session.add(manual_version)
    await session.flush()
    chapter.selected_version_id = manual_version.id

    chapter.status = "successful"
    chapter.word_count = len(request.content or "")
    await session.commit()

    background_tasks.add_task(
        _refresh_edit_summary_and_ingest,
        project_id,
        request.chapter_number,
        request.content,
        current_user.id,
    )

    stmt = (
        select(Chapter)
        .options(
            selectinload(Chapter.versions),
            selectinload(Chapter.evaluations),
            selectinload(Chapter.selected_version),
        )
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == request.chapter_number,
        )
    )
    result = await session.execute(stmt)
    chapter = result.scalars().first()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    outline_stmt = select(ChapterOutline).where(
        ChapterOutline.project_id == project_id,
        ChapterOutline.chapter_number == request.chapter_number,
    )
    outline_result = await session.execute(outline_stmt)
    outline = outline_result.scalars().first()

    title = outline.title if outline else f"第{request.chapter_number}章"
    summary = outline.summary if outline else ""
    real_summary = chapter.real_summary
    content = chapter.selected_version.content if chapter.selected_version else None
    versions = (
        [v.content for v in sorted(chapter.versions, key=lambda item: item.created_at)]
        if chapter.versions
        else None
    )
    evaluation_text = None
    if chapter.evaluations:
        latest = sorted(chapter.evaluations, key=lambda item: item.created_at)[-1]
        evaluation_text = latest.feedback or latest.decision
    status_value = chapter.status or ChapterGenerationStatus.NOT_GENERATED.value

    return ChapterSchema(
        chapter_number=request.chapter_number,
        title=title,
        summary=summary,
        real_summary=real_summary,
        content=content,
        versions=versions,
        evaluation=evaluation_text,
        generation_status=ChapterGenerationStatus(status_value),
        word_count=chapter.word_count or 0,
    )
