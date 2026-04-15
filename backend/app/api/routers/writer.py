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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
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
from ...services.generation_task_runner import generation_task_runner
from ...services.generation_task_service import (
    ACTIVE_TASK_STATUSES,
    FAILED_TASK_STATUSES,
    TASK_STATUS_CANCELED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_QUEUED,
    TASK_TYPE_CHAPTER_GENERATION,
    GenerationTaskService,
)
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


def _queue_state_from_task_status(task_status: str) -> Literal["active", "failed", "done", "other"]:
    if task_status in ACTIVE_TASK_STATUSES:
        return "active"
    if task_status in FAILED_TASK_STATUSES:
        return "failed"
    if task_status == TASK_STATUS_COMPLETED:
        return "done"
    return "other"


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


async def _build_writer_task_center_response(
    *,
    project_id: str,
    user_id: int,
    limit: int,
    status_group: Literal["active", "failed", "all"],
    session: AsyncSession,
) -> WriterTaskCenterResponse:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit 必须在 1~500 之间")

    novel_service = NovelService(session)
    task_service = GenerationTaskService(session)
    await novel_service.ensure_project_owner(project_id, user_id)

    stmt = (
        select(Chapter)
        .options(selectinload(Chapter.evaluations))
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.updated_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()

    all_tasks = await task_service.list_recent_tasks(
        project_id=project_id,
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        limit=max(200, limit * 5),
    )
    latest_task_by_chapter: dict[int, Any] = {}
    for task in all_tasks:
        chapter_no = task.chapter_number
        if chapter_no is None:
            continue
        if chapter_no not in latest_task_by_chapter:
            latest_task_by_chapter[chapter_no] = task

    now = datetime.utcnow()
    items: list[WriterTaskCenterItem] = []
    active_count = 0
    failed_count = 0
    done_count = 0

    for chapter in rows:
        status_value = (chapter.status or "not_generated").strip() or "not_generated"
        latest_task = latest_task_by_chapter.get(chapter.chapter_number)
        item_status = status_value

        if latest_task:
            queue_state = _queue_state_from_task_status(latest_task.status)
            progress_percent = int(latest_task.progress_percent or 0)
            stage_label = latest_task.stage_label or "处理中"
            status_message = latest_task.status_message or "任务执行中"
            item_status = latest_task.status
            task_id = latest_task.id
            can_cancel = bool(
                latest_task.status in ACTIVE_TASK_STATUSES
                and int(latest_task.user_id) == int(user_id)
            )
            can_retry = bool(latest_task.status in FAILED_TASK_STATUSES)
            error_message = latest_task.error_message if latest_task.status in FAILED_TASK_STATUSES else None
        else:
            queue_state = _writer_queue_state(status_value)
            progress_percent, stage_label, status_message = _writer_progress(status_value)
            task_id = _build_writer_task_id(chapter.project_id, chapter.chapter_number)
            can_cancel = False
            can_retry = queue_state == "failed"
            error_message = None

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

        if queue_state == "failed" and not error_message and chapter.evaluations:
            failed_evals = [
                item for item in chapter.evaluations
                if ((item.decision or "").strip().lower() == "failed") and item.feedback
            ]
            if failed_evals:
                latest_failed = sorted(failed_evals, key=lambda item: item.created_at)[-1]
                error_message = latest_failed.feedback
        if queue_state == "failed" and not error_message:
            error_message = "任务失败，请重试。"

        if status_group == "active" and queue_state != "active":
            continue
        if status_group == "failed" and queue_state != "failed":
            continue

        items.append(
            WriterTaskCenterItem(
                task_id=task_id,
                chapter_id=chapter.id,
                project_id=chapter.project_id,
                chapter_number=chapter.chapter_number,
                status=item_status,
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


@router.get("/novels/{project_id}/tasks", response_model=WriterTaskCenterResponse)
async def get_writer_task_center(
    project_id: str,
    limit: int = 80,
    status_group: Literal["active", "failed", "all"] = "all",
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WriterTaskCenterResponse:
    return await _build_writer_task_center_response(
        project_id=project_id,
        user_id=int(current_user.id),
        limit=limit,
        status_group=status_group,
        session=session,
    )


@router.get("/novels/{project_id}/tasks/stream")
async def stream_writer_task_center(
    project_id: str,
    request: Request,
    limit: int = 120,
    status_group: Literal["active", "failed", "all"] = "all",
    interval_seconds: int = 3,
    current_user: UserInDB = Depends(get_current_user),
) -> StreamingResponse:
    if interval_seconds < 1 or interval_seconds > 15:
        raise HTTPException(status_code=400, detail="interval_seconds 必须在 1~15 之间")

    async def _event_stream():
        last_snapshot = ""
        while True:
            if await request.is_disconnected():
                break

            try:
                async with AsyncSessionLocal() as stream_session:
                    snapshot = await _build_writer_task_center_response(
                        project_id=project_id,
                        user_id=int(current_user.id),
                        limit=limit,
                        status_group=status_group,
                        session=stream_session,
                    )
                serialized = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False)
                if serialized != last_snapshot:
                    last_snapshot = serialized
                    yield f"event: snapshot\ndata: {serialized}\n\n"
                else:
                    yield "event: ping\ndata: {}\n\n"
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("任务中心 SSE 推送失败: project=%s error=%s", project_id, exc)
                payload = json.dumps({"message": str(exc)[:200]}, ensure_ascii=False)
                yield f"event: error\ndata: {payload}\n\n"

            await asyncio.sleep(interval_seconds)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/novels/{project_id}/tasks/{chapter_number}/cancel", response_model=WriterTaskCenterCancelResponse)
async def cancel_writer_task(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WriterTaskCenterCancelResponse:
    novel_service = NovelService(session)
    task_service = GenerationTaskService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    latest_task = await task_service.get_latest_task(
        project_id=project_id,
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        chapter_number=chapter_number,
        statuses=ACTIVE_TASK_STATUSES,
    )
    if not latest_task:
        raise HTTPException(status_code=409, detail="当前任务未在运行中，无法取消")
    if int(latest_task.user_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="无权取消该任务")

    await task_service.request_cancel(latest_task.id)
    if latest_task.status == TASK_STATUS_QUEUED:
        chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
        chapter.status = ChapterGenerationStatus.FAILED.value
    await generation_task_runner.cancel_running_task(latest_task.id)
    await session.commit()

    return WriterTaskCenterCancelResponse(
        accepted=True,
        task_id=latest_task.id,
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
    task_service = GenerationTaskService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, chapter_number)
    if not outline:
        raise HTTPException(status_code=400, detail="缺少章节大纲，无法重试生成")

    chapter = await novel_service.get_or_create_chapter(project_id, chapter_number)
    previous_status = (chapter.status or "not_generated").strip() or "not_generated"
    active_task = await task_service.get_active_task(
        project_id=project_id,
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        chapter_number=chapter_number,
    )
    if active_task:
        if not payload.force:
            raise HTTPException(status_code=409, detail="任务正在执行中，若要重试请开启 force")
        await task_service.request_cancel(active_task.id)
        await generation_task_runner.cancel_running_task(active_task.id)

    if previous_status not in _WRITER_FAILED_STATUSES and not payload.force:
        raise HTTPException(status_code=400, detail="当前任务不是失败状态，若要重试请开启 force")

    latest_failed_task = await task_service.get_latest_task(
        project_id=project_id,
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        chapter_number=chapter_number,
        statuses={TASK_STATUS_FAILED, TASK_STATUS_CANCELED},
    )
    resume_variants: list[dict] = []
    resumed_variant_count = 0
    if payload.resume_from_checkpoint and latest_failed_task and isinstance(latest_failed_task.checkpoint, dict):
        maybe_variants = latest_failed_task.checkpoint.get("generated_variants")
        if isinstance(maybe_variants, list):
            resume_variants = [item for item in maybe_variants if isinstance(item, dict)]
            resumed_variant_count = len(resume_variants)

    chapter.real_summary = None
    chapter.selected_version_id = None
    chapter.status = ChapterGenerationStatus.GENERATING.value
    flow_config: Dict[str, Any] = {"preset": "basic"}
    requested_versions = await _resolve_version_count(session)
    flow_config["versions"] = requested_versions
    task = await task_service.create_task(
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        project_id=project_id,
        user_id=current_user.id,
        chapter_number=chapter_number,
        retry_count=(latest_failed_task.retry_count + 1) if latest_failed_task else 1,
        resume_from_task_id=latest_failed_task.id if latest_failed_task else None,
        payload={
            "writing_notes": payload.writing_notes,
            "flow_config": flow_config,
            "resume_variants": resume_variants,
        },
    )
    generation_task_runner.enqueue(task.id)
    await session.commit()

    message = (
        f"继续任务已提交（已复用 {resumed_variant_count} 个已生成版本）"
        if resumed_variant_count > 0
        else "重试任务已提交"
    )
    return WriterTaskCenterRetryResponse(
        accepted=True,
        task_id=task.id,
        project_id=project_id,
        chapter_number=chapter_number,
        previous_status=previous_status,
        message=message,
    )


@router.post("/novels/{project_id}/chapters/generate", response_model=NovelProjectSchema)
async def generate_chapter(
    project_id: str,
    request: GenerateChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    task_service = GenerationTaskService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    outline = await novel_service.get_outline(project_id, request.chapter_number)
    if not outline:
        raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

    existing_active = await task_service.get_active_task(
        project_id=project_id,
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        chapter_number=request.chapter_number,
    )
    if existing_active:
        return await _load_project_schema(novel_service, project_id, current_user.id)

    chapter = await novel_service.get_or_create_chapter(project_id, request.chapter_number)
    if chapter.status == ChapterGenerationStatus.GENERATING.value:
        chapter.status = ChapterGenerationStatus.FAILED.value

    latest_failed_task = await task_service.get_latest_task(
        project_id=project_id,
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        chapter_number=request.chapter_number,
        statuses={TASK_STATUS_FAILED, TASK_STATUS_CANCELED},
    )
    resume_variants: list[dict] = []
    if latest_failed_task and isinstance(latest_failed_task.checkpoint, dict):
        maybe_variants = latest_failed_task.checkpoint.get("generated_variants")
        if isinstance(maybe_variants, list):
            resume_variants = [item for item in maybe_variants if isinstance(item, dict)]

    version_count = await _resolve_version_count(session)
    flow_config: Dict[str, Any] = {
        "preset": "basic",
        "versions": version_count,
    }

    chapter.real_summary = None
    chapter.selected_version_id = None
    chapter.status = ChapterGenerationStatus.GENERATING.value
    task = await task_service.create_task(
        task_type=TASK_TYPE_CHAPTER_GENERATION,
        project_id=project_id,
        chapter_number=request.chapter_number,
        user_id=current_user.id,
        retry_count=(latest_failed_task.retry_count + 1) if latest_failed_task else 0,
        resume_from_task_id=latest_failed_task.id if latest_failed_task else None,
        payload={
            "writing_notes": request.writing_notes,
            "flow_config": flow_config,
            "resume_variants": resume_variants,
        },
    )
    generation_task_runner.enqueue(task.id)
    await session.commit()

    logger.info(
        "章节任务已加入队列: project=%s chapter=%s user=%s task_id=%s resume_variants=%s",
        project_id,
        request.chapter_number,
        current_user.id,
        task.id,
        len(resume_variants),
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
