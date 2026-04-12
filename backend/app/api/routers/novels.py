# AIMETA P=小说API_项目和章节管理|R=小说CRUD_章节管理|NR=不含内容生成|E=route:GET_POST_/api/novels/*|X=http|A=小说CRUD_章节|D=fastapi,sqlalchemy|S=db|RD=./README.ai
import json
import logging
import os
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import AsyncSessionLocal, get_session
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


def _ensure_prompt(prompt: str | None, name: str) -> str:
    if not prompt:
        raise HTTPException(status_code=500, detail=f"未配置名为 {name} 的提示词，请联系管理员")
    return prompt


def _resolve_blueprint_timeout_seconds() -> float:
    raw = os.getenv("BLUEPRINT_GENERATE_TIMEOUT_SECONDS", "420").strip()
    try:
        value = float(raw)
    except ValueError:
        return 420.0
    return max(60.0, min(540.0, value))


def _resolve_blueprint_poll_interval_seconds() -> int:
    raw = os.getenv("BLUEPRINT_ASYNC_POLL_INTERVAL_SECONDS", "5").strip()
    try:
        value = int(raw)
    except ValueError:
        return 5
    return max(2, min(15, value))


def _build_formatted_history(history_records: List) -> List[Dict[str, str]]:
    formatted_history: List[Dict[str, str]] = []
    for record in history_records:
        role = record.role
        content = record.content
        if not role or not content:
            continue
        try:
            normalized = unwrap_markdown_json(content)
            data = json.loads(normalized)
            if role == "user":
                user_value = data.get("value", data)
                if isinstance(user_value, str):
                    formatted_history.append({"role": "user", "content": user_value})
            elif role == "assistant":
                ai_message = data.get("ai_message") if isinstance(data, dict) else None
                if ai_message:
                    formatted_history.append({"role": "assistant", "content": ai_message})
        except (json.JSONDecodeError, AttributeError):
            continue
    return formatted_history


def _blueprint_completion_message() -> str:
    return "太棒了！我已经根据我们的对话整理出完整的小说蓝图。请确认是否进入写作阶段，或提出修改意见。"


async def _generate_blueprint_for_project(
    session: AsyncSession,
    *,
    project_id: str,
    user_id: int,
) -> BlueprintGenerationResponse:
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    project = await novel_service.ensure_project_owner(project_id, user_id)
    logger.info("项目 %s 开始生成蓝图", project_id)

    history_records = await novel_service.list_conversations(project_id)
    if not history_records:
        logger.warning("项目 %s 缺少对话历史，无法生成蓝图", project_id)
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    formatted_history = _build_formatted_history(history_records)
    if not formatted_history:
        logger.warning("项目 %s 对话历史格式异常，无法提取有效内容", project_id)
        raise HTTPException(
            status_code=400,
            detail="无法从历史对话中提取有效内容，请检查对话历史格式或重新进行概念对话",
        )

    project.status = "blueprint_generating"
    await session.commit()

    try:
        system_prompt = _ensure_prompt(await prompt_service.get_prompt("screenwriting"), "screenwriting")
        blueprint_timeout = _resolve_blueprint_timeout_seconds()
        blueprint_raw = await llm_service.get_llm_response(
            system_prompt=system_prompt,
            conversation_history=formatted_history,
            temperature=0.3,
            user_id=user_id,
            timeout=blueprint_timeout,
            project_id=project_id,
            request_type="blueprint",
            max_retries_override=0,
            allow_fallback_models=False,
        )
        blueprint_raw = remove_think_tags(blueprint_raw)

        blueprint_normalized = unwrap_markdown_json(blueprint_raw)
        blueprint_sanitized = sanitize_json_like_text(blueprint_normalized)
        try:
            blueprint_data = json.loads(blueprint_sanitized)
        except json.JSONDecodeError as exc:
            logger.error(
                "项目 %s 蓝图生成 JSON 解析失败: %s\n原始响应: %s\n标准化后: %s\n清洗后: %s",
                project_id,
                exc,
                blueprint_raw[:500],
                blueprint_normalized[:500],
                blueprint_sanitized[:500],
            )
            raise HTTPException(
                status_code=500,
                detail=f"蓝图生成失败，AI 返回的内容格式不正确。请重试或联系管理员。错误详情: {str(exc)}",
            ) from exc

        blueprint = Blueprint(**blueprint_data)
        await novel_service.replace_blueprint(project_id, blueprint)
        if blueprint.title:
            project.title = blueprint.title
        project.status = "blueprint_ready"
        await session.commit()
        logger.info("项目 %s 蓝图生成完成并标记为 blueprint_ready", project_id)

        return BlueprintGenerationResponse(
            blueprint=blueprint,
            ai_message=_blueprint_completion_message(),
        )
    except Exception:
        project.status = "blueprint_failed"
        await session.commit()
        raise


async def _generate_blueprint_async_task(project_id: str, user_id: int) -> None:
    async with AsyncSessionLocal() as bg_session:
        try:
            await _generate_blueprint_for_project(
                bg_session,
                project_id=project_id,
                user_id=user_id,
            )
            logger.info("项目 %s 异步蓝图生成任务执行完成", project_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("项目 %s 异步蓝图生成任务失败: %s", project_id, exc)
            try:
                novel_service = NovelService(bg_session)
                project = await novel_service.ensure_project_owner(project_id, user_id)
                project.status = "blueprint_failed"
                await bg_session.commit()
            except Exception:
                await bg_session.rollback()
                logger.exception("项目 %s 异步蓝图失败状态写回失败", project_id)


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

    parsed.setdefault("conversation_state", parsed.get("conversation_state", {}))
    return ConverseResponse(**parsed)


@router.post("/{project_id}/blueprint/generate", response_model=BlueprintGenerationResponse)
async def generate_blueprint(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationResponse:
    """根据完整对话生成可执行的小说蓝图。"""
    return await _generate_blueprint_for_project(
        session,
        project_id=project_id,
        user_id=current_user.id,
    )


@router.post("/{project_id}/blueprint/generate-async", response_model=BlueprintGenerationAsyncAccepted)
async def generate_blueprint_async(
    project_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> BlueprintGenerationAsyncAccepted:
    """异步触发蓝图生成，立即返回任务受理状态。"""
    novel_service = NovelService(session)
    project = await novel_service.ensure_project_owner(project_id, current_user.id)

    # 先做基础校验，避免提交无效任务
    history_records = await novel_service.list_conversations(project_id)
    if not history_records:
        raise HTTPException(status_code=400, detail="缺少对话历史，请先完成概念对话后再生成蓝图")

    if (project.status or "").strip() == "blueprint_generating":
        return BlueprintGenerationAsyncAccepted(
            project_id=project_id,
            status="running",
            message="蓝图正在生成中，请稍后刷新状态",
            poll_interval_seconds=_resolve_blueprint_poll_interval_seconds(),
        )

    project.status = "blueprint_generating"
    await session.commit()

    background_tasks.add_task(
        _generate_blueprint_async_task,
        project_id,
        current_user.id,
    )
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
    project = await novel_service.ensure_project_owner(project_id, current_user.id)
    status_value = (project.status or "").strip()

    if status_value == "blueprint_generating":
        return BlueprintGenerationStatusResponse(
            project_id=project_id,
            status="generating",
        )

    if status_value == "blueprint_failed":
        return BlueprintGenerationStatusResponse(
            project_id=project_id,
            status="failed",
            error_message="蓝图生成失败，请检查模型配置或稍后重试",
        )

    # 兼容历史数据：已有蓝图也视为完成
    project_schema = await novel_service.get_project_schema(project_id, current_user.id)
    if project_schema.blueprint:
        return BlueprintGenerationStatusResponse(
            project_id=project_id,
            status="completed",
            blueprint=project_schema.blueprint,
            ai_message=_blueprint_completion_message(),
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
