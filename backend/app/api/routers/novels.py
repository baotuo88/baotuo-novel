# AIMETA P=小说API_项目和章节管理|R=小说CRUD_章节管理|NR=不含内容生成|E=route:GET_POST_/api/novels/*|X=http|A=小说CRUD_章节|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import json
import logging
import os
import re
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.novel import (
    Blueprint,
    BlueprintGenerationAsyncAccepted,
    BlueprintGenerationResponse,
    BlueprintGenerationStatusResponse,
    BlueprintPatch,
    Chapter as ChapterSchema,
    ConverseRequest,
    ConverseResponse,
    NovelProject as NovelProjectSchema,
    NovelProjectSummary,
    NovelSectionResponse,
    NovelSectionType,
)
from ...schemas.user import UserInDB
from ...services.import_service import ImportService
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.blueprint_generation_service import (
    _ensure_prompt,
    blueprint_completion_message,
    generate_blueprint_for_project,
)
from ...services.generation_task_runner import generation_task_runner
from ...services.generation_task_service import (
    TASK_STATUS_CANCELED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_QUEUED,
    TASK_STATUS_RUNNING,
    TASK_TYPE_BLUEPRINT_GENERATION,
    GenerationTaskService,
)
from ...utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/novels", tags=["Novels"])

JSON_RESPONSE_INSTRUCTION = """
IMPORTANT: 你的回复必须是合法的 JSON 对象，并严格包含以下字段：
{
  "ai_message": "string",
  "ui_control": {
    "type": "single_choice | text_input | info_display",
    "options": [
      {"id": "option_1", "label": "string"}
    ],
    "placeholder": "string"
  },
  "conversation_state": {},
  "is_complete": false
}
不要输出额外的文本或解释。
"""


_CHOICE_LINE_PATTERN = re.compile(r"^\s*([A-Z])[\)\）\.\、:：]\s*(.+?)\s*$")


def _extract_choice_options_from_message(message: str) -> List[Dict[str, str]]:
    """从 AI 文本中提取 A/B/C 形式选项，兜底生成按钮。"""
    if not message:
        return []

    options: List[Dict[str, str]] = []
    seen_ids: set[str] = set()

    for raw_line in message.splitlines():
        line = (raw_line or "").strip()
        if not line:
            continue
        matched = _CHOICE_LINE_PATTERN.match(line)
        if not matched:
            continue

        option_id = matched.group(1).lower()
        if option_id in seen_ids:
            continue

        label = matched.group(2).strip()
        if " (" in label:
            label = label.split(" (", 1)[0].strip()
        if "（" in label:
            label = label.split("（", 1)[0].strip()
        if not label:
            continue

        options.append({"id": option_id, "label": label})
        seen_ids.add(option_id)
        if len(options) >= 12:
            break

    return options


def _normalize_choice_options(raw_options: Any) -> List[Dict[str, str]]:
    """将模型返回 options 归一化为 [{id,label}]。"""
    if not isinstance(raw_options, list):
        return []

    normalized: List[Dict[str, str]] = []
    seen_ids: set[str] = set()

    for item in raw_options:
        option_id = ""
        label = ""

        if isinstance(item, dict):
            option_id = str(item.get("id", "")).strip().lower()
            label = str(item.get("label", "")).strip()
        elif isinstance(item, str):
            label = item.strip()
            option_id = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")

        if not label:
            continue
        if not option_id:
            option_id = f"option-{len(normalized) + 1}"
        if option_id in seen_ids:
            continue

        normalized.append({"id": option_id, "label": label})
        seen_ids.add(option_id)

    return normalized


def _normalize_converse_payload(payload: dict) -> dict:
    """兜底修正 LLM 对话返回，避免因字段缺失导致 500。"""
    normalized = dict(payload or {})

    ai_message = normalized.get("ai_message")
    if isinstance(ai_message, str):
        normalized["ai_message"] = ai_message
    elif ai_message is None:
        normalized["ai_message"] = "我已收到你的设想，我们继续完善细节。"
    else:
        normalized["ai_message"] = str(ai_message)

    is_complete = normalized.get("is_complete")
    normalized["is_complete"] = bool(is_complete)

    conversation_state = normalized.get("conversation_state")
    normalized["conversation_state"] = conversation_state if isinstance(conversation_state, dict) else {}

    ui_control = normalized.get("ui_control")
    if not isinstance(ui_control, dict):
        ui_control = {}
    control_type = str(ui_control.get("type") or "").strip()
    if control_type not in {"single_choice", "text_input", "info_display"}:
        control_type = "text_input"

    options = _normalize_choice_options(ui_control.get("options"))
    inferred_options = _extract_choice_options_from_message(normalized["ai_message"])
    if inferred_options and not options:
        options = inferred_options
    if options:
        control_type = "single_choice"
    elif control_type == "single_choice":
        # 避免 single_choice 无选项导致前端“看起来可选但无法点击”。
        control_type = "text_input"

    normalized["ui_control"] = {
        "type": control_type,
        "options": options or None,
        "placeholder": ui_control.get("placeholder") or "请输入你的补充设想...",
    }
    return normalized


def _resolve_blueprint_poll_interval_seconds() -> int:
    raw = os.getenv("BLUEPRINT_ASYNC_POLL_INTERVAL_SECONDS", "5").strip()
    try:
        value = int(raw)
    except ValueError:
        return 5
    return max(2, min(15, value))


@router.post("", response_model=NovelProjectSchema, status_code=status.HTTP_201_CREATED)
async def create_novel(
    title: str = Body(...),
    initial_prompt: str = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """为当前用户创建一个新的小说项目。"""
    novel_service = NovelService(session)
    project = await novel_service.create_project(current_user.id, title, initial_prompt)
    logger.info("用户 %s 创建项目 %s", current_user.id, project.id)
    return await novel_service.get_project_schema(project.id, current_user.id)


@router.post("/import", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
async def import_novel(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    """上传并导入小说文件。"""
    import_service = ImportService(session)
    project_id = await import_service.import_novel_from_file(current_user.id, file)
    logger.info("用户 %s 导入项目 %s", current_user.id, project_id)
    return {"id": project_id}


@router.get("", response_model=List[NovelProjectSummary])
async def list_novels(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[NovelProjectSummary]:
    """列出用户的全部小说项目摘要信息。"""
    novel_service = NovelService(session)
    projects = await novel_service.list_projects_for_user(current_user.id)
    logger.info("用户 %s 获取项目列表，共 %s 个", current_user.id, len(projects))
    return projects


@router.get("/{project_id}", response_model=NovelProjectSchema)
async def get_novel(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 查询项目 %s", current_user.id, project_id)
    return await novel_service.get_project_schema(project_id, current_user.id)


@router.get("/{project_id}/sections/{section}", response_model=NovelSectionResponse)
async def get_novel_section(
    project_id: str,
    section: NovelSectionType,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelSectionResponse:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 的 %s 区段", current_user.id, project_id, section)
    return await novel_service.get_section_data(project_id, current_user.id, section)


@router.get("/{project_id}/chapters/{chapter_number}", response_model=ChapterSchema)
async def get_chapter(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ChapterSchema:
    novel_service = NovelService(session)
    logger.info("用户 %s 获取项目 %s 第 %s 章", current_user.id, project_id, chapter_number)
    return await novel_service.get_chapter_schema(project_id, current_user.id, chapter_number)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_novels(
    project_ids: List[str] = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    novel_service = NovelService(session)
    await novel_service.delete_projects(project_ids, current_user.id)
    logger.info("用户 %s 删除项目 %s", current_user.id, project_ids)
    return {"status": "success", "message": f"成功删除 {len(project_ids)} 个项目"}


@router.post("/{project_id}/concept/converse", response_model=ConverseResponse)
async def converse_with_concept(
    project_id: str,
    request: ConverseRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ConverseResponse:
    """与概念设计师（LLM）进行对话，引导蓝图筹备。"""
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    history_records = await novel_service.list_conversations(project_id)
    logger.info(
        "项目 %s 概念对话请求，用户 %s，历史记录 %s 条",
        project_id,
        current_user.id,
        len(history_records),
    )
    conversation_history = [
        {"role": record.role, "content": record.content}
        for record in history_records
    ]
    user_content = json.dumps(request.user_input, ensure_ascii=False)
    conversation_history.append({"role": "user", "content": user_content})

    system_prompt = _ensure_prompt(await prompt_service.get_prompt("concept"), "concept")
    system_prompt = f"{system_prompt}\n{JSON_RESPONSE_INSTRUCTION}"

    llm_response = await llm_service.get_llm_response(
        system_prompt=system_prompt,
        conversation_history=conversation_history,
        temperature=0.8,
        user_id=current_user.id,
        timeout=240.0,
        project_id=project_id,
    )
    llm_response = remove_think_tags(llm_response)

    try:
        normalized = unwrap_markdown_json(llm_response)
        sanitized = sanitize_json_like_text(normalized)
        parsed = json.loads(sanitized)
    except json.JSONDecodeError as exc:
        logger.exception(
            "Failed to parse concept converse response: project_id=%s user_id=%s error=%s\nOriginal response: %s\nNormalized: %s\nSanitized: %s",
            project_id,
            current_user.id,
            exc,
            llm_response[:1000],
            normalized[:1000] if 'normalized' in locals() else "N/A",
            sanitized[:1000] if 'sanitized' in locals() else "N/A",
        )
        raise HTTPException(
            status_code=500,
            detail=f"概念对话失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}"
        ) from exc

    await novel_service.append_conversation(project_id, "user", user_content)
    await novel_service.append_conversation(project_id, "assistant", normalized)

    logger.info("项目 %s 概念对话完成，is_complete=%s", project_id, parsed.get("is_complete"))

    if parsed.get("is_complete"):
        parsed["ready_for_blueprint"] = True

    parsed = _normalize_converse_payload(parsed)
    try:
        return ConverseResponse(**parsed)
    except ValidationError as exc:
        logger.exception(
            "概念对话响应结构校验失败: project_id=%s user_id=%s error=%s parsed=%s",
            project_id,
            current_user.id,
            exc,
            json.dumps(parsed, ensure_ascii=False)[:1200],
        )
        raise HTTPException(
            status_code=500,
            detail="概念对话失败，AI 返回结构不完整，请重试一次。若多次失败请检查模型提示词与返回格式。",
        ) from exc


@router.post("/{project_id}/blueprint/generate", response_model=BlueprintGenerationResponse)
async def generate_blueprint(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationResponse:
    """根据完整对话生成可执行的小说蓝图。"""
    return await generate_blueprint_for_project(
        session,
        project_id=project_id,
        user_id=current_user.id,
    )


@router.post("/{project_id}/blueprint/generate-async", response_model=BlueprintGenerationAsyncAccepted)
async def generate_blueprint_async(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationAsyncAccepted:
    """异步触发蓝图生成，立即返回任务受理状态。"""
    novel_service = NovelService(session)
    task_service = GenerationTaskService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 先做基础校验，避免提交无效任务
    history_records = await novel_service.list_conversations(project_id)
    if not history_records:
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    active_task = await task_service.get_active_task(
        project_id=project_id,
        task_type=TASK_TYPE_BLUEPRINT_GENERATION,
        chapter_number=None,
    )
    if active_task:
        return BlueprintGenerationAsyncAccepted(
            project_id=project_id,
            status="running",
            message="蓝图正在生成中，请稍后刷新状态",
            poll_interval_seconds=_resolve_blueprint_poll_interval_seconds(),
        )

    project.status = "blueprint_generating"
    await session.commit()

    task = await task_service.create_task(
        task_type=TASK_TYPE_BLUEPRINT_GENERATION,
        project_id=project_id,
        user_id=current_user.id,
        payload={},
    )
    generation_task_runner.enqueue(task.id)
    return BlueprintGenerationAsyncAccepted(
        project_id=project_id,
        status="accepted",
        message="蓝图生成任务已提交",
        poll_interval_seconds=_resolve_blueprint_poll_interval_seconds(),
    )


@router.get("/{project_id}/blueprint/status", response_model=BlueprintGenerationStatusResponse)
async def get_blueprint_status(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationStatusResponse:
    """查询蓝图异步生成状态。"""
    novel_service = NovelService(session)
    task_service = GenerationTaskService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    latest_task = await task_service.get_latest_task(
        project_id=project_id,
        task_type=TASK_TYPE_BLUEPRINT_GENERATION,
        chapter_number=None,
    )

    project_schema = await novel_service.get_project_schema(project_id, current_user.id)
    if project_schema.blueprint and not (latest_task and latest_task.status in {TASK_STATUS_QUEUED, TASK_STATUS_RUNNING}):
        return BlueprintGenerationStatusResponse(
            project_id=project_id,
            status="completed",
            blueprint=project_schema.blueprint,
            ai_message=blueprint_completion_message(),
        )

    if latest_task and latest_task.status in {TASK_STATUS_QUEUED, TASK_STATUS_RUNNING}:
        return BlueprintGenerationStatusResponse(
            project_id=project_id,
            status="generating",
        )

    if latest_task and latest_task.status in {TASK_STATUS_FAILED, TASK_STATUS_CANCELED}:
        return BlueprintGenerationStatusResponse(
            project_id=project_id,
            status="failed",
            error_message=latest_task.error_message or "蓝图生成失败，请检查模型配置或稍后重试",
        )

    # 兼容历史数据：已有蓝图或任务已完成都视为完成
    if project_schema.blueprint or (latest_task and latest_task.status == TASK_STATUS_COMPLETED):
        return BlueprintGenerationStatusResponse(
            project_id=project_id,
            status="completed",
            blueprint=project_schema.blueprint,
            ai_message=blueprint_completion_message(),
        )

    return BlueprintGenerationStatusResponse(
        project_id=project_id,
        status="not_started",
    )


@router.post("/{project_id}/blueprint/save", response_model=NovelProjectSchema)
async def save_blueprint(
    project_id: str,
    blueprint_data: Blueprint | None = Body(None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """保存蓝图信息，可用于手动覆盖自动生成结果。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    if blueprint_data:
        await novel_service.replace_blueprint(project_id, blueprint_data)
        if blueprint_data.title:
            project.title = blueprint_data.title
            await session.commit()
        logger.info("项目 %s 手动保存蓝图", project_id)
    else:
        logger.warning("项目 %s 保存蓝图时未提供蓝图数据", project_id)
        raise HTTPException(status_code=400, detail="缺少蓝图数据，请提供有效的蓝图内容")

    return await novel_service.get_project_schema(project_id, current_user.id)


@router.patch("/{project_id}/blueprint", response_model=NovelProjectSchema)
async def patch_blueprint(
    project_id: str,
    payload: BlueprintPatch,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> NovelProjectSchema:
    """局部更新蓝图字段，对世界观或角色做微调。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    update_data = payload.model_dump(exclude_unset=True)
    await novel_service.patch_blueprint(project_id, update_data)
    logger.info("项目 %s 局部更新蓝图字段：%s", project_id, list(update_data.keys()))
    return await novel_service.get_project_schema(project_id, current_user.id)
