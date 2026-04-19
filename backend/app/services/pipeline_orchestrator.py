# AIMETA P=写作流水线编排_统一生成入口|R=上下文汇聚_生成_审查_优化|NR=不含API路由|E=PipelineOrchestrator|X=internal|A=编排器|D=fastapi,sqlalchemy|S=db,net|RD=./README.ai
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.novel import Chapter
from ..models.project_memory import ProjectMemory
from ..repositories.system_config_repository import SystemConfigRepository
from ..services.ai_review_service import AIReviewService
from ..services.chapter_context_service import ChapterContextService
from ..services.chapter_guardrails import ChapterGuardrails
from ..services.consistency_service import ConsistencyService, ViolationSeverity
from ..services.enhanced_writing_flow import EnhancedWritingFlow
from ..services.enrichment_service import EnrichmentService
from ..services.llm_service import LLMService
from ..services.knowledge_retrieval_service import KnowledgeRetrievalService, FilteredContext
from ..services.memory_layer_service import MemoryLayerService
from ..services.novel_service import NovelService
from ..services.preview_generation_service import PreviewGenerationService
from ..services.prompt_service import PromptService
from ..services.reader_simulator_service import ReaderSimulatorService, ReaderType
from ..services.self_critique_service import CritiqueDimension, SelfCritiqueService
from ..services.vector_store_service import VectorStoreService
from ..services.writer_context_builder import WriterContextBuilder
from ..utils.json_utils import remove_think_tags, unwrap_markdown_json

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    preset: str = "basic"
    version_count: int = 2
    enable_preview: bool = False
    enable_optimizer: bool = False
    enable_consistency: bool = False
    enable_enrichment: bool = False
    async_finalize: bool = False
    enable_constitution: bool = False
    enable_persona: bool = False
    enable_six_dimension: bool = False
    enable_reader_sim: bool = False
    enable_self_critique: bool = False
    enable_memory: bool = False
    enable_rag: bool = True
    rag_mode: str = "simple"
    enable_foreshadowing: bool = False
    enable_faction: bool = False


class PipelineOrchestrator:
    """统一写作流水线编排器。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm_service = LLMService(session)
        self.prompt_service = PromptService(session)
        self.novel_service = NovelService(session)
        self.context_builder = WriterContextBuilder()
        self.guardrails = ChapterGuardrails()

    async def generate_chapter(
        self,
        *,
        project_id: str,
        chapter_number: int,
        user_id: int,
        writing_notes: Optional[str] = None,
        flow_config: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
        variant_callback: Optional[Callable[[List[Dict[str, Any]]], Awaitable[None]]] = None,
        resume_variants: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        config = await self._resolve_config(flow_config)
        await self._emit_progress(progress_callback, 5, "准备上下文", "正在加载项目与章节信息")
        project = await self.novel_service.ensure_project_owner(project_id, user_id)

        outline = await self.novel_service.get_outline(project_id, chapter_number)
        if not outline:
            raise HTTPException(status_code=404, detail="蓝图中未找到对应章节纲要")

        chapter = await self.novel_service.get_or_create_chapter(project_id, chapter_number)
        chapter.real_summary = None
        chapter.selected_version_id = None
        chapter.status = "generating"
        await self.session.commit()
        await self._emit_progress(progress_callback, 12, "整理历史上下文", "正在整合前文摘要与上下文")

        outlines_map = {item.chapter_number: item for item in project.outlines}
        history_context = await self._collect_history_context(
            project_id=project_id,
            chapter_number=chapter_number,
            outlines_map=outlines_map,
            chapters=project.chapters,
            user_id=user_id,
        )
        recent_memory_pack = await self._build_recent_memory_pack(
            completed_chapters=history_context["completed_chapters"],
            chapter_number=chapter_number,
        )
        recent_retrieval_seed = await self._build_recent_retrieval_seed(
            completed_chapters=history_context["completed_chapters"],
            chapter_number=chapter_number,
        )

        project_schema = await self.novel_service._serialize_project(project)
        blueprint_dict = self._normalize_blueprint(project_schema.blueprint.model_dump())

        outline_title = outline.title or f"第{outline.chapter_number}章"
        outline_summary = outline.summary or "暂无摘要"

        preset_context = await self.prompt_service.get_active_writing_preset_context(project_id=project_id)
        project_memory = await self._get_project_memory(project_id)
        raw_writing_notes = (writing_notes or "").strip()
        writing_notes_parts: List[str] = []
        preset_notes_prefix = str(preset_context.get("writing_notes_prefix") or "").strip() if preset_context else ""
        if preset_notes_prefix:
            writing_notes_parts.append(preset_notes_prefix)
        if raw_writing_notes:
            writing_notes_parts.append(raw_writing_notes)
        terminology_constraints_text = self._build_terminology_constraints_text(project_memory)
        if terminology_constraints_text:
            writing_notes_parts.append(terminology_constraints_text)
        writing_notes = "\n".join(writing_notes_parts) if writing_notes_parts else "无额外写作指令"

        all_characters = [c.get("name") for c in blueprint_dict.get("characters", []) if c.get("name")]

        chapter_mission = await self._generate_chapter_mission(
            blueprint_dict=blueprint_dict,
            previous_summary=history_context["previous_summary"],
            previous_tail=history_context["previous_tail"],
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            introduced_characters=[],
            all_characters=all_characters,
            user_id=user_id,
            project_id=project_id,
        )

        allowed_new_characters = chapter_mission.get("allowed_new_characters", []) if chapter_mission else []

        visibility_context = self.context_builder.build_visibility_context(
            blueprint=blueprint_dict,
            completed_summaries=history_context["completed_summaries"],
            previous_tail=history_context["previous_tail"],
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            allowed_new_characters=allowed_new_characters,
        )

        writer_blueprint = visibility_context["writer_blueprint"]
        forbidden_characters = visibility_context["forbidden_characters"]
        introduced_characters = visibility_context["introduced_characters"]

        logger.info(
            "Pipeline context: project=%s chapter=%s introduced=%d allowed_new=%d forbidden=%d",
            project_id,
            chapter_number,
            len(introduced_characters),
            len(allowed_new_characters),
            len(forbidden_characters),
        )

        enhanced_flow = None
        enhanced_context = None
        if config.enable_constitution or config.enable_persona or config.enable_foreshadowing or config.enable_faction:
            enhanced_flow = EnhancedWritingFlow(self.session, self.llm_service, self.prompt_service)
            enhanced_context = await enhanced_flow.prepare_writing_context(
                project_id=project_id,
                chapter_number=chapter_number,
                chapter_outline=outline_summary,
            )

        memory_context = None
        if config.enable_memory:
            memory_context = await self._get_memory_context(
                project_id=project_id,
                chapter_number=chapter_number,
                involved_characters=introduced_characters,
            )

        project_memory_text = self._format_project_memory_text(project_memory)

        rag_context = None
        knowledge_context = None
        rag_stats = None
        if config.enable_rag:
            if config.rag_mode == "two_stage":
                knowledge_context, rag_stats = await self._get_two_stage_rag_context(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    writing_notes=writing_notes,
                    pov_character=self._resolve_pov_character(chapter_mission),
                    user_id=user_id,
                    recent_retrieval_seed=recent_retrieval_seed,
                )
            else:
                rag_context = await self._get_rag_context(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    writing_notes=writing_notes,
                    user_id=user_id,
                    recent_retrieval_seed=recent_retrieval_seed,
                )
                rag_stats = {
                    "mode": "simple",
                    "chunks": len(rag_context.get("chunks", [])) if rag_context else 0,
                    "summaries": len(rag_context.get("summaries", [])) if rag_context else 0,
                }

        preferred_prompt_name = str(preset_context.get("prompt_name") or "writing_v2").strip() if preset_context else "writing_v2"
        writer_prompt = await self.prompt_service.get_prompt(preferred_prompt_name)
        if not writer_prompt and preferred_prompt_name != "writing_v2":
            writer_prompt = await self.prompt_service.get_prompt("writing_v2")
        if not writer_prompt:
            writer_prompt = await self.prompt_service.get_prompt("writing")
        if not writer_prompt:
            raise HTTPException(status_code=500, detail="缺少写作提示词，请联系管理员配置")

        generation_temperature = float(preset_context.get("temperature")) if preset_context else 0.9
        generation_top_p = float(preset_context["top_p"]) if preset_context and preset_context.get("top_p") is not None else None
        generation_max_tokens = (
            int(preset_context["max_tokens"]) if preset_context and preset_context.get("max_tokens") is not None else None
        )
        preset_style_rules_text = str(preset_context.get("style_rules_text") or "").strip() if preset_context else ""
        writing_preset_meta = (
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
        )
        if writing_preset_meta:
            logger.info(
                "Pipeline preset enabled: project=%s chapter=%s preset=%s prompt=%s temperature=%.2f top_p=%s max_tokens=%s",
                project_id,
                chapter_number,
                writing_preset_meta["preset_id"],
                preferred_prompt_name,
                generation_temperature,
                generation_top_p,
                generation_max_tokens,
            )

        prompt_sections = self._build_prompt_sections(
            writer_blueprint=writer_blueprint,
            previous_summary=history_context["previous_summary"],
            previous_tail=history_context["previous_tail"],
            chapter_mission=chapter_mission,
            rag_context=rag_context,
            knowledge_context=knowledge_context,
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            forbidden_characters=forbidden_characters,
            project_memory_text=project_memory_text,
            memory_context=memory_context,
            recent_memory_pack=recent_memory_pack,
            preset_style_rules_text=preset_style_rules_text,
        )

        if enhanced_flow and enhanced_context:
            prompt_sections = enhanced_flow.build_enhanced_prompt_sections(prompt_sections, enhanced_context)

        prompt_input = "\n\n".join(f"{title}\n{content}" for title, content in prompt_sections if content)
        logger.debug("Pipeline prompt length: %s chars", len(prompt_input))
        await self._emit_progress(progress_callback, 22, "准备生成", "已完成上下文准备，开始生成候选版本")

        version_count = config.version_count
        version_style_hints = self._resolve_style_hints(enhanced_context, version_count)

        versions: List[Dict[str, Any]] = self._sanitize_resume_variants(resume_variants, version_count)
        start_index = len(versions)
        for idx in range(start_index, version_count):
            style_hint = version_style_hints[idx] if idx < len(version_style_hints) else None
            await self._emit_progress(
                progress_callback,
                25 + int((idx / max(1, version_count)) * 35),
                "生成候选版本",
                f"正在生成第 {idx + 1}/{version_count} 个候选版本",
            )
            versions.append(
                await self._generate_single_version(
                    index=idx,
                    prompt_input=prompt_input,
                    writer_prompt=writer_prompt,
                    style_hint=style_hint,
                    project_id=project_id,
                    chapter_number=chapter_number,
                    outline_title=outline_title,
                    outline_summary=outline_summary,
                    chapter_mission=chapter_mission,
                    forbidden_characters=forbidden_characters,
                    allowed_new_characters=allowed_new_characters,
                    user_id=user_id,
                    writer_blueprint=writer_blueprint,
                    memory_context=memory_context,
                    enhanced_context=enhanced_context,
                    config=config,
                    generation_temperature=generation_temperature,
                    generation_top_p=generation_top_p,
                    generation_max_tokens=generation_max_tokens,
                    writing_preset_meta=writing_preset_meta,
                )
            )
            if variant_callback:
                await variant_callback(versions)

        await self._emit_progress(progress_callback, 66, "评审候选版本", "正在评审并挑选最佳版本")
        best_version_index, ai_review_result = await self._run_ai_review(
            versions=versions,
            chapter_mission=chapter_mission,
            user_id=user_id,
        )

        review_summaries: Dict[str, Any] = {}
        if ai_review_result:
            review_summaries["ai_review"] = ai_review_result

        if versions:
            best_version_index = max(0, min(best_version_index, len(versions) - 1))
        else:
            best_version_index = 0

        if versions:
            best_version = versions[best_version_index]
            best_content = best_version["content"]

            if enhanced_flow and config.enable_six_dimension:
                review_result = await enhanced_flow.post_generation_review(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    chapter_title=outline_title,
                    chapter_content=best_content,
                    chapter_plan=json.dumps(chapter_mission, ensure_ascii=False) if chapter_mission else None,
                    previous_summary=history_context["previous_summary"],
                )
                review_summaries["enhanced_review"] = review_result

            if config.enable_self_critique:
                best_content, critique_summary = await self._run_self_critique(
                    best_content,
                    user_id=user_id,
                    context={
                        "character_profiles": json.dumps(writer_blueprint.get("characters", []), ensure_ascii=False),
                        "previous_summary": history_context["previous_summary"],
                    },
                )
                review_summaries["self_critique"] = critique_summary

            if config.enable_reader_sim:
                reader_feedback = await self._run_reader_simulation(
                    best_content,
                    chapter_number=chapter_number,
                    previous_summary=history_context["previous_summary"],
                    user_id=user_id,
                )
                review_summaries["reader_simulator"] = reader_feedback

            if config.enable_consistency:
                best_content, consistency_report = await self._run_consistency_check(
                    project_id=project_id,
                    chapter_text=best_content,
                    user_id=user_id,
                )
                review_summaries["consistency"] = consistency_report

            if config.enable_optimizer:
                best_content, optimizer_report = await self._run_optimizer(
                    best_content,
                    user_id=user_id,
                    project_id=project_id,
                )
                review_summaries["optimizer"] = optimizer_report

            if config.enable_enrichment:
                best_content, enrichment_report = await self._run_enrichment(
                    best_content,
                    user_id=user_id,
                )
                if enrichment_report:
                    review_summaries["enrichment"] = enrichment_report

            best_version["content"] = best_content
            best_version.setdefault("metadata", {})["review_summaries"] = review_summaries

        contents = [v.get("content", "") for v in versions]
        metadata = [v.get("metadata") for v in versions]
        await self._emit_progress(progress_callback, 88, "写入章节版本", "正在保存候选版本并更新章节状态")
        versions_models = await self.novel_service.replace_chapter_versions(chapter, contents, metadata)

        variants = []
        for idx, version_model in enumerate(versions_models):
            variant = {
                "index": idx,
                "version_id": version_model.id,
                "content": versions[idx].get("content", ""),
                "metadata": versions[idx].get("metadata"),
            }
            variants.append(variant)

        await self._emit_progress(progress_callback, 100, "完成", "章节生成完成")
        return {
            "project_id": project_id,
            "chapter_number": chapter_number,
            "preset": config.preset,
            "best_version_index": best_version_index,
            "variants": variants,
            "review_summaries": review_summaries,
            "debug_metadata": {
                "version_count": version_count,
                "stages": self._build_stage_flags(config),
                "retrieval_stats": rag_stats,
            },
        }

    @staticmethod
    async def _emit_progress(
        callback: Optional[Callable[[int, str, str], Awaitable[None]]],
        progress: int,
        stage: str,
        message: str,
    ) -> None:
        if not callback:
            return
        await callback(max(0, min(100, int(progress))), stage, message)

    @staticmethod
    def _sanitize_resume_variants(
        resume_variants: Optional[List[Dict[str, Any]]],
        version_count: int,
    ) -> List[Dict[str, Any]]:
        if not resume_variants:
            return []
        normalized: List[Dict[str, Any]] = []
        for idx, item in enumerate(resume_variants):
            if idx >= version_count:
                break
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            normalized.append(
                {
                    "index": idx,
                    "content": content,
                    "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                }
            )
        return normalized

    async def _resolve_config(self, flow_config: Optional[Dict[str, Any]]) -> PipelineConfig:
        flow_config = flow_config or {}
        preset = flow_config.get("preset", "basic")

        config = PipelineConfig(preset=preset)
        config.version_count = await self._resolve_version_count(flow_config.get("versions"))

        if preset in ("enhanced", "ultimate"):
            config.enable_constitution = True
            config.enable_persona = True
            config.enable_foreshadowing = True
            config.enable_faction = True
            config.rag_mode = "two_stage"

        if preset == "enhanced":
            config.enable_six_dimension = True

        if preset == "ultimate":
            config.enable_memory = True

        if preset == "basic":
            config.enable_rag = True

        for key in (
            "enable_preview",
            "enable_optimizer",
            "enable_consistency",
            "enable_enrichment",
            "async_finalize",
            "enable_rag",
        ):
            if key in flow_config and flow_config[key] is not None:
                setattr(config, key, bool(flow_config[key]))

        if flow_config.get("rag_mode"):
            config.rag_mode = str(flow_config["rag_mode"])

        if preset == "ultimate":
            config.enable_preview = False
            config.enable_optimizer = False
            config.enable_consistency = False
            config.enable_enrichment = False
            config.enable_six_dimension = False
            config.enable_reader_sim = False
            config.enable_self_critique = False

        return config

    async def _resolve_version_count(self, requested_count: Optional[int]) -> int:
        if requested_count:
            try:
                count = int(requested_count)
                return max(1, count)
            except (TypeError, ValueError):
                pass

        repo = SystemConfigRepository(self.session)
        for key in ("writer.chapter_versions", "writer.version_count"):
            record = await repo.get_by_key(key)
            if record and record.value:
                try:
                    val = int(record.value)
                    if val >= 1:
                        return val
                except ValueError:
                    pass

        for env in ("WRITER_CHAPTER_VERSION_COUNT", "WRITER_CHAPTER_VERSIONS", "WRITER_VERSION_COUNT"):
            v = os.getenv(env)
            if v:
                try:
                    val = int(v)
                    if val >= 1:
                        return val
                except ValueError:
                    pass

        return int(settings.writer_chapter_versions)

    async def _get_system_config_value(self, key: str) -> Optional[str]:
        repo = SystemConfigRepository(self.session)
        record = await repo.get_by_key(key)
        if record and record.value not in (None, ""):
            return str(record.value)
        env_key = key.upper().replace(".", "_")
        return os.getenv(env_key)

    async def _get_int_system_config(
        self,
        key: str,
        *,
        default: int,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> int:
        raw = await self._get_system_config_value(key)
        value = default
        if raw not in (None, ""):
            try:
                value = int(str(raw).strip())
            except Exception:
                logger.warning("系统配置 %s 非法整数值：%s，回退默认值 %s", key, raw, default)
                value = default
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    async def _get_float_system_config(
        self,
        key: str,
        *,
        default: float,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ) -> float:
        raw = await self._get_system_config_value(key)
        value = default
        if raw not in (None, ""):
            try:
                value = float(str(raw).strip())
            except Exception:
                logger.warning("系统配置 %s 非法浮点值：%s，回退默认值 %.4f", key, raw, default)
                value = default
        if min_value is not None:
            value = max(min_value, value)
        if max_value is not None:
            value = min(max_value, value)
        return value

    async def _build_recent_memory_pack(
        self,
        *,
        completed_chapters: List[Dict[str, Any]],
        chapter_number: int,
    ) -> Optional[str]:
        if not completed_chapters:
            return None

        memory_limit = await self._get_int_system_config(
            "rag.long_memory.recent_summary_count",
            default=6,
            min_value=1,
            max_value=24,
        )
        max_item_chars = await self._get_int_system_config(
            "rag.long_memory.recent_summary_chars",
            default=260,
            min_value=80,
            max_value=1200,
        )
        picked = completed_chapters[-memory_limit:]
        lines: List[str] = []
        for item in picked:
            number = int(item.get("chapter_number") or 0)
            title = str(item.get("title") or f"第{number}章").strip() or f"第{number}章"
            summary = str(item.get("summary") or "").strip()
            if not summary:
                continue
            if len(summary) > max_item_chars:
                summary = summary[: max_item_chars - 1] + "…"
            lines.append(f"- 第{number}章《{title}》：{summary}")

        if not lines:
            return None
        return (
            f"当前准备创作第{chapter_number}章，请优先延续最近剧情脉络并保持因果连续：\n"
            + "\n".join(lines)
        )

    async def _build_recent_retrieval_seed(
        self,
        *,
        completed_chapters: List[Dict[str, Any]],
        chapter_number: int,
    ) -> Optional[str]:
        if not completed_chapters:
            return None
        seed_limit = await self._get_int_system_config(
            "rag.long_memory.retrieval_seed_count",
            default=4,
            min_value=1,
            max_value=12,
        )
        picked = completed_chapters[-seed_limit:]
        lines: List[str] = [f"检索补充线索（第{chapter_number}章写作前）:"]
        for item in picked:
            number = int(item.get("chapter_number") or 0)
            title = str(item.get("title") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if not title and not summary:
                continue
            summary_brief = summary[:120] + "…" if len(summary) > 120 else summary
            lines.append(f"- 第{number}章 {title} {summary_brief}".strip())
        if len(lines) <= 1:
            return None
        return "\n".join(lines)

    @staticmethod
    def _truncate_context_lines(lines: List[str], max_chars: int) -> List[str]:
        if max_chars <= 0 or not lines:
            return []
        output: List[str] = []
        total = 0
        for line in lines:
            text = str(line or "").strip()
            if not text:
                continue
            length = len(text)
            if total + length <= max_chars:
                output.append(text)
                total += length
                continue
            remain = max_chars - total
            if remain > 60 and not output:
                output.append(text[: remain - 1] + "…")
            break
        return output

    async def _collect_history_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outlines_map: Dict[int, Any],
        chapters: List[Chapter],
        user_id: int,
    ) -> Dict[str, Any]:
        completed_summaries = []
        completed_chapters = []
        latest_prev_number = -1
        previous_summary_text = ""
        previous_tail_excerpt = ""

        for existing in chapters:
            if existing.chapter_number >= chapter_number:
                continue
            if existing.selected_version is None or not existing.selected_version.content:
                continue
            if not existing.real_summary:
                summary = await self.llm_service.get_summary(
                    existing.selected_version.content,
                    temperature=0.15,
                    user_id=user_id,
                    timeout=180.0,
                    project_id=project_id,
                )
                existing.real_summary = remove_think_tags(summary)
                await self.session.commit()

            completed_chapters.append(
                {
                    "chapter_number": existing.chapter_number,
                    "title": outlines_map.get(existing.chapter_number).title
                    if outlines_map.get(existing.chapter_number)
                    else f"第{existing.chapter_number}章",
                    "summary": existing.real_summary,
                }
            )
            completed_summaries.append(existing.real_summary or "")

            if existing.chapter_number > latest_prev_number:
                latest_prev_number = existing.chapter_number
                previous_summary_text = existing.real_summary or ""
                previous_tail_excerpt = self._extract_tail_excerpt(existing.selected_version.content)

        return {
            "completed_chapters": completed_chapters,
            "completed_summaries": completed_summaries,
            "previous_summary": previous_summary_text or "暂无（这是第一章）",
            "previous_tail": previous_tail_excerpt or "暂无（这是第一章）",
        }

    @staticmethod
    def _extract_tail_excerpt(text: Optional[str], limit: int = 500) -> str:
        if not text:
            return ""
        stripped = text.strip()
        if len(stripped) <= limit:
            return stripped
        return stripped[-limit:]

    @staticmethod
    def _normalize_blueprint(blueprint_dict: Dict[str, Any]) -> Dict[str, Any]:
        if "relationships" in blueprint_dict and blueprint_dict["relationships"]:
            for relation in blueprint_dict["relationships"]:
                if "character_from" in relation:
                    relation["from"] = relation.pop("character_from")
                if "character_to" in relation:
                    relation["to"] = relation.pop("character_to")
        return blueprint_dict

    async def _generate_chapter_mission(
        self,
        *,
        blueprint_dict: Dict[str, Any],
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
        plan_prompt = await self.prompt_service.get_prompt("chapter_plan")
        if not plan_prompt:
            logger.warning("未配置 chapter_plan 提示词，跳过导演脚本生成")
            return None

        plan_input = f"""
[上一章摘要]
{previous_summary}

[上一章结尾]
{previous_tail}

[当前章节大纲]
标题：{outline_title}
摘要：{outline_summary}

[已登场角色]
{json.dumps(introduced_characters, ensure_ascii=False) if introduced_characters else "暂无"}

[全部角色]
{json.dumps(all_characters, ensure_ascii=False)}

[写作指令]
{writing_notes}
"""

        try:
            response = await self.llm_service.get_llm_response(
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
            logger.info("章节导演脚本生成完成: macro_beat=%s", mission.get("macro_beat"))
            return mission
        except Exception as exc:
            logger.warning("生成章节导演脚本失败，将使用默认模式: %s", exc)
            return None

    async def _get_rag_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        user_id: int,
        recent_retrieval_seed: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not settings.vector_store_enabled:
            return {"chunks": [], "summaries": []}

        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过 RAG: %s", exc)
            return {"chunks": [], "summaries": []}

        query_parts = [outline_title, outline_summary]
        if writing_notes:
            query_parts.append(writing_notes)
        if recent_retrieval_seed:
            query_parts.append(recent_retrieval_seed)
        rag_query = "\n".join(part for part in query_parts if part)

        top_k_chunks = await self._get_int_system_config(
            "rag.simple.top_k_chunks",
            default=settings.vector_top_k_chunks,
            min_value=0,
            max_value=50,
        )
        top_k_summaries = await self._get_int_system_config(
            "rag.simple.top_k_summaries",
            default=settings.vector_top_k_summaries,
            min_value=0,
            max_value=50,
        )
        recency_weight = await self._get_float_system_config(
            "rag.long_memory.recency_weight",
            default=0.08,
            min_value=0.0,
            max_value=1.5,
        )
        max_context_chars = await self._get_int_system_config(
            "rag.long_memory.max_context_chars",
            default=9000,
            min_value=1000,
            max_value=48000,
        )

        context_service = ChapterContextService(llm_service=self.llm_service, vector_store=vector_store)
        rag_context = await context_service.retrieve_for_generation(
            project_id=project_id,
            query_text=rag_query or outline_title or outline_summary,
            user_id=user_id,
            top_k_chunks=top_k_chunks,
            top_k_summaries=top_k_summaries,
            target_chapter_number=chapter_number,
            recency_weight=recency_weight,
        )
        chunks = rag_context.chunk_texts() if rag_context.chunks else []
        summaries = rag_context.summary_lines() if rag_context.summaries else []
        chunk_budget = int(max_context_chars * 0.75)
        summary_budget = max_context_chars - chunk_budget
        chunks = self._truncate_context_lines(chunks, chunk_budget)
        summaries = self._truncate_context_lines(summaries, summary_budget)
        return {
            "chunks": chunks,
            "summaries": summaries,
        }

    async def _get_two_stage_rag_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        writing_notes: str,
        pov_character: Optional[str],
        user_id: int,
        recent_retrieval_seed: Optional[str] = None,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        if not settings.vector_store_enabled:
            return None, {"mode": "two_stage", "enabled": False}

        try:
            vector_store = VectorStoreService()
        except RuntimeError as exc:
            logger.warning("向量库初始化失败，跳过两层 RAG: %s", exc)
            return None, {"mode": "two_stage", "enabled": False, "error": str(exc)}

        sync_session = getattr(self.session, "sync_session", self.session)
        retrieval_service = KnowledgeRetrievalService(sync_session, self.llm_service, vector_store)
        two_stage_top_k = await self._get_int_system_config(
            "rag.two_stage.top_k",
            default=settings.vector_top_k_chunks,
            min_value=1,
            max_value=50,
        )
        guidance_parts = [writing_notes.strip()] if writing_notes and writing_notes.strip() else []
        if recent_retrieval_seed:
            guidance_parts.append(recent_retrieval_seed)
        merged_guidance = "\n".join(guidance_parts) if guidance_parts else None
        filtered = await retrieval_service.retrieve_and_filter(
            project_id=project_id,
            chapter_number=chapter_number,
            user_id=user_id,
            pov_character=pov_character,
            user_guidance=merged_guidance,
            top_k=two_stage_top_k,
        )
        context_text = self._format_filtered_context(filtered)
        stats = filtered.stats or {}
        stats["mode"] = "two_stage"
        return context_text, stats

    async def _get_project_memory(self, project_id: str) -> Optional[ProjectMemory]:
        result = await self.session.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        )
        return result.scalars().first()

    @staticmethod
    def _normalize_terminology_entries(raw_items: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []

        normalized: List[Dict[str, Any]] = []
        seen_terms: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue

            term = str(item.get("term") or "").strip()
            if not term:
                continue
            term_key = term.lower()
            if term_key in seen_terms:
                continue

            canonical = str(item.get("canonical") or "").strip() or term
            canonical_key = canonical.lower()
            aliases: List[str] = []
            seen_aliases: set[str] = set()
            aliases_raw = item.get("aliases")
            if isinstance(aliases_raw, list):
                for alias in aliases_raw:
                    alias_text = str(alias or "").strip()
                    if not alias_text:
                        continue
                    alias_key = alias_text.lower()
                    if alias_key in seen_aliases or alias_key == canonical_key:
                        continue
                    aliases.append(alias_text)
                    seen_aliases.add(alias_key)

            normalized.append(
                {
                    "term": term,
                    "canonical": canonical,
                    "aliases": aliases,
                    "category": str(item.get("category") or "").strip() or None,
                    "note": str(item.get("note") or "").strip() or None,
                    "enforce": bool(item.get("enforce", True)),
                }
            )
            seen_terms.add(term_key)

        normalized.sort(key=lambda entry: entry["term"].lower())
        return normalized

    def _build_terminology_constraints_text(self, memory: Optional[ProjectMemory]) -> Optional[str]:
        if not memory or not isinstance(memory.extra, dict):
            return None

        entries = self._normalize_terminology_entries(memory.extra.get("terminology_dictionary"))
        enforced_entries = [item for item in entries if bool(item.get("enforce", True))]
        if not enforced_entries:
            return None

        lines: List[str] = []
        for item in enforced_entries[:30]:
            term = str(item.get("term") or "").strip()
            canonical = str(item.get("canonical") or "").strip() or term
            aliases = [str(alias).strip() for alias in (item.get("aliases") or []) if str(alias).strip()]
            note = str(item.get("note") or "").strip()

            suffix_parts: List[str] = []
            if aliases:
                suffix_parts.append(f"别名：{'、'.join(aliases)}")
            if note:
                suffix_parts.append(f"说明：{note}")
            suffix = f"（{'；'.join(suffix_parts)}）" if suffix_parts else ""

            if canonical == term and not aliases:
                lines.append(f"- 术语“{canonical}”保持固定写法{suffix}")
            else:
                lines.append(f"- 术语“{term}”统一写作“{canonical}”{suffix}")

        if not lines:
            return None
        return "【术语词典一致性约束】\n涉及以下术语时必须统一使用规范写法，不得混用：\n" + "\n".join(lines)

    def _format_project_memory_text(self, memory: Optional[ProjectMemory]) -> Optional[str]:
        if not memory:
            return None

        parts: List[str] = []
        if memory.global_summary:
            parts.append(f"### 全局摘要\n{memory.global_summary}")
        if memory.story_timeline_summary:
            parts.append(f"### 故事时间线摘要\n{memory.story_timeline_summary}")
        if memory.plot_arcs:
            parts.append("### 剧情线追踪\n" + json.dumps(memory.plot_arcs, ensure_ascii=False, indent=2))

        terminology_entries: List[Dict[str, Any]] = []
        if isinstance(memory.extra, dict):
            terminology_entries = self._normalize_terminology_entries(memory.extra.get("terminology_dictionary"))
        if terminology_entries:
            glossary_lines: List[str] = []
            for item in terminology_entries[:20]:
                term = str(item.get("term") or "").strip()
                canonical = str(item.get("canonical") or "").strip() or term
                aliases = [str(alias).strip() for alias in (item.get("aliases") or []) if str(alias).strip()]
                category = str(item.get("category") or "").strip()
                note = str(item.get("note") or "").strip()
                prefix = f"[{category}] " if category else ""
                alias_text = f"（别名：{'、'.join(aliases)}）" if aliases else ""
                note_text = f"；备注：{note}" if note else ""
                glossary_lines.append(f"- {prefix}{term} -> {canonical}{alias_text}{note_text}")
            parts.append("### 术语词典\n" + "\n".join(glossary_lines))

        if not parts:
            return None
        return "\n\n".join(parts)

    async def _get_memory_context(
        self,
        *,
        project_id: str,
        chapter_number: int,
        involved_characters: List[str],
    ) -> str:
        memory_layer = MemoryLayerService(self.session, self.llm_service, self.prompt_service)
        return await memory_layer.get_memory_context(project_id, chapter_number, involved_characters)

    @staticmethod
    def _build_prompt_sections(
        *,
        writer_blueprint: Dict[str, Any],
        previous_summary: str,
        previous_tail: str,
        chapter_mission: Optional[dict],
        rag_context: Optional[Dict[str, Any]],
        knowledge_context: Optional[str],
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        forbidden_characters: List[str],
        project_memory_text: Optional[str],
        memory_context: Optional[str],
        recent_memory_pack: Optional[str],
        preset_style_rules_text: Optional[str],
    ) -> List[Tuple[str, str]]:
        blueprint_text = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)
        mission_text = json.dumps(chapter_mission, ensure_ascii=False, indent=2) if chapter_mission else "无导演脚本"
        forbidden_text = json.dumps(forbidden_characters, ensure_ascii=False) if forbidden_characters else "无"

        sections: List[Tuple[str, str]] = [
            ("[世界蓝图](JSON，已裁剪)", blueprint_text),
        ]

        if project_memory_text:
            sections.append(("[项目长期记忆](摘要/剧情线)", project_memory_text))
        if memory_context:
            sections.append(("[记忆层上下文]", memory_context))

        sections.extend(
            [
                ("[上一章摘要]", previous_summary or "暂无（这是第一章）"),
                ("[上一章结尾]", previous_tail or "暂无（这是第一章）"),
                ("[长篇记忆库](最近章节脉络)", recent_memory_pack or ""),
                ("[章节导演脚本](JSON)", mission_text),
            ]
        )

        if knowledge_context:
            sections.append(("[RAG精筛上下文](含POV裁剪)", knowledge_context))

        if rag_context:
            rag_chunks_text = "\n\n".join(rag_context.get("chunks", [])) or "未检索到章节片段"
            rag_summaries_text = "\n".join(rag_context.get("summaries", [])) or "未检索到章节摘要"
            sections.append(("[检索到的剧情上下文](Markdown)", rag_chunks_text))
            sections.append(("[检索到的章节摘要](Markdown)", rag_summaries_text))

        if preset_style_rules_text:
            sections.append(("[写作Preset风格规则](严格遵循)", preset_style_rules_text))

        sections.extend(
            [
                ("[当前章节目标]", f"标题：{outline_title}\n摘要：{outline_summary}\n写作要求：{writing_notes}"),
                ("[禁止角色](本章不允许提及)", forbidden_text),
            ]
        )

        return sections

    @staticmethod
    def _resolve_style_hints(
        enhanced_context: Optional[Dict[str, Any]],
        version_count: int,
    ) -> List[str]:
        if enhanced_context and enhanced_context.get("version_style_hints"):
            hints = enhanced_context["version_style_hints"]
            if isinstance(hints, list) and hints:
                return hints[:version_count]
        return [
            "情绪更细腻，节奏更慢，多写内心戏和感官描写",
            "冲突更强，节奏更快，多写动作和对话",
            "悬念更重，多埋伏笔，结尾钩子更强",
        ][:version_count]

    @staticmethod
    def _resolve_pov_character(chapter_mission: Optional[dict]) -> Optional[str]:
        if not chapter_mission:
            return None
        return chapter_mission.get("pov") or chapter_mission.get("pov_character")

    async def _generate_single_version(
        self,
        *,
        index: int,
        prompt_input: str,
        writer_prompt: str,
        style_hint: Optional[str],
        project_id: str,
        chapter_number: int,
        outline_title: str,
        outline_summary: str,
        chapter_mission: Optional[dict],
        forbidden_characters: List[str],
        allowed_new_characters: List[str],
        user_id: int,
        writer_blueprint: Dict[str, Any],
        memory_context: Optional[str],
        enhanced_context: Optional[Dict[str, Any]],
        config: PipelineConfig,
        generation_temperature: float,
        generation_top_p: Optional[float],
        generation_max_tokens: Optional[int],
        writing_preset_meta: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "chapter_mission": chapter_mission,
            "style_hint": style_hint,
            "pipeline": {"preset": config.preset},
        }
        if writing_preset_meta:
            metadata["writing_preset"] = writing_preset_meta

        content = ""
        if config.enable_preview:
            content, preview_meta = await self._generate_with_preview(
                project_id=project_id,
                chapter_number=chapter_number,
                outline_title=outline_title,
                outline_summary=outline_summary,
                writer_blueprint=writer_blueprint,
                memory_context=memory_context,
                style_hint=style_hint,
                enhanced_context=enhanced_context,
                user_id=user_id,
            )
            metadata["preview"] = preview_meta

        if not content:
            final_prompt_input = prompt_input
            if style_hint:
                final_prompt_input += f"\n\n[版本风格提示]\n{style_hint}"

            response = await self.llm_service.get_llm_response(
                system_prompt=writer_prompt,
                conversation_history=[{"role": "user", "content": final_prompt_input}],
                temperature=generation_temperature,
                user_id=user_id,
                timeout=600.0,
                response_format=None,
                max_tokens=generation_max_tokens,
                top_p=generation_top_p,
                project_id=project_id,
            )
            cleaned = remove_think_tags(response)
            content = unwrap_markdown_json(cleaned)

        guardrail_result = self.guardrails.check(
            generated_text=content,
            forbidden_characters=forbidden_characters,
            allowed_new_characters=allowed_new_characters,
            pov=chapter_mission.get("pov") if chapter_mission else None,
        )
        guardrail_metadata = {"passed": guardrail_result.passed, "violations": []}

        if not guardrail_result.passed:
            guardrail_metadata["violations"] = [
                {"type": v.type, "severity": v.severity, "description": v.description}
                for v in guardrail_result.violations
            ]
            violations_text = self.guardrails.format_violations_for_rewrite(guardrail_result)
            content = await self._rewrite_with_guardrails(
                original_text=content,
                chapter_mission=chapter_mission,
                violations_text=violations_text,
                user_id=user_id,
                project_id=project_id,
            )

        parsed_json = None
        extracted_text = None
        try:
            parsed_json = json.loads(content)
            extracted_text = self._extract_text(parsed_json)
        except Exception:
            parsed_json = None

        metadata["guardrail"] = guardrail_metadata
        if parsed_json is not None:
            metadata["parsed_json"] = parsed_json

        return {
            "index": index,
            "content": extracted_text or content,
            "metadata": metadata,
        }

    async def _generate_with_preview(
        self,
        *,
        project_id: str,
        chapter_number: int,
        outline_title: str,
        outline_summary: str,
        writer_blueprint: Dict[str, Any],
        memory_context: Optional[str],
        style_hint: Optional[str],
        enhanced_context: Optional[Dict[str, Any]],
        user_id: int,
    ) -> Tuple[str, Dict[str, Any]]:
        preview_service = PreviewGenerationService(self.session, self.llm_service, self.prompt_service)
        blueprint_context = json.dumps(writer_blueprint, ensure_ascii=False, indent=2)

        extra_constraints = []
        if enhanced_context:
            if enhanced_context.get("constitution"):
                extra_constraints.append(enhanced_context["constitution"])
            if enhanced_context.get("writer_persona"):
                extra_constraints.append(enhanced_context["writer_persona"])

        if extra_constraints:
            blueprint_context = blueprint_context + "\n\n" + "\n\n".join(extra_constraints)

        preview_result = await preview_service.generate_with_preview(
            project_id=project_id,
            chapter_number=chapter_number,
            outline={"title": outline_title, "summary": outline_summary},
            blueprint_context=blueprint_context,
            emotion_context="（无情绪曲线指导）",
            memory_context=memory_context or "（无记忆层上下文）",
            style_hint=style_hint or "",
            user_id=user_id,
        )

        return preview_result.get("full_chapter", ""), preview_result

    async def _rewrite_with_guardrails(
        self,
        *,
        original_text: str,
        chapter_mission: Optional[dict],
        violations_text: str,
        user_id: int,
        project_id: Optional[str] = None,
    ) -> str:
        rewrite_prompt = await self.prompt_service.get_prompt("rewrite_guardrails")
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
            response = await self.llm_service.get_llm_response(
                system_prompt=rewrite_prompt,
                conversation_history=[{"role": "user", "content": rewrite_input}],
                temperature=0.3,
                user_id=user_id,
                timeout=300.0,
                response_format=None,
                project_id=project_id,
            )
            cleaned = remove_think_tags(response)
            return cleaned
        except Exception as exc:
            logger.warning("自动修复失败，返回原文: %s", exc)
            return original_text

    @staticmethod
    def _extract_text(value: object) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            for key in ("content", "chapter_content", "chapter_text", "text", "body", "story"):
                if value.get(key):
                    nested = PipelineOrchestrator._extract_text(value.get(key))
                    if nested:
                        return nested
            return None
        if isinstance(value, list):
            for item in value:
                nested = PipelineOrchestrator._extract_text(item)
                if nested:
                    return nested
        return None

    async def _run_ai_review(
        self,
        *,
        versions: List[Dict[str, Any]],
        chapter_mission: Optional[dict],
        user_id: int,
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        if len(versions) <= 1:
            return 0, None

        contents = [v.get("content", "") for v in versions]
        try:
            ai_review_service = AIReviewService(self.llm_service, self.prompt_service)
            ai_review_result = await ai_review_service.review_versions(
                versions=contents,
                chapter_mission=chapter_mission,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("AI 评审失败，跳过: %s", exc)
            return 0, None

        if not ai_review_result:
            return 0, None

        for idx, variant in enumerate(versions):
            variant.setdefault("metadata", {})["ai_review"] = {
                "is_best": idx == ai_review_result.best_version_index,
                "scores": ai_review_result.scores,
                "evaluation": ai_review_result.overall_evaluation if idx == ai_review_result.best_version_index else None,
                "flaws": ai_review_result.critical_flaws if idx == ai_review_result.best_version_index else None,
                "suggestions": ai_review_result.refinement_suggestions if idx == ai_review_result.best_version_index else None,
            }

        return ai_review_result.best_version_index, {
            "best_version_index": ai_review_result.best_version_index,
            "scores": ai_review_result.scores,
            "evaluation": ai_review_result.overall_evaluation,
            "flaws": ai_review_result.critical_flaws,
            "suggestions": ai_review_result.refinement_suggestions,
        }

    async def _run_self_critique(
        self,
        chapter_content: str,
        *,
        user_id: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        service = SelfCritiqueService(self.session, self.llm_service, self.prompt_service)
        critique = await service.critique_and_revise_loop(
            chapter_content=chapter_content,
            max_iterations=1,
            target_score=75.0,
            dimensions=[
                CritiqueDimension.LOGIC,
                CritiqueDimension.CHARACTER,
                CritiqueDimension.WRITING,
            ],
            context=context,
            user_id=user_id,
        )
        return critique.get("final_content", chapter_content), {
            "iterations": len(critique.get("iterations", [])),
            "final_score": critique.get("final_score", 0),
            "improvement": critique.get("improvement", 0),
            "status": critique.get("status", "unknown"),
        }

    async def _run_reader_simulation(
        self,
        chapter_content: str,
        *,
        chapter_number: int,
        previous_summary: Optional[str],
        user_id: int,
    ) -> Dict[str, Any]:
        service = ReaderSimulatorService(self.session, self.llm_service, self.prompt_service)
        return await service.simulate_reading_experience(
            chapter_content=chapter_content,
            chapter_number=chapter_number,
            reader_types=[ReaderType.THRILL_SEEKER, ReaderType.CRITIC, ReaderType.CASUAL],
            previous_summary=previous_summary,
            user_id=user_id,
        )

    async def _run_consistency_check(
        self,
        *,
        project_id: str,
        chapter_text: str,
        user_id: int,
    ) -> Tuple[str, Dict[str, Any]]:
        sync_session = getattr(self.session, "sync_session", self.session)
        service = ConsistencyService(sync_session, self.llm_service)
        result = await service.check_consistency(project_id, chapter_text, user_id, include_foreshadowing=True)
        report = {
            "is_consistent": result.is_consistent,
            "summary": result.summary,
            "check_time_ms": result.check_time_ms,
            "violations": [
                {
                    "severity": v.severity.value if hasattr(v.severity, "value") else v.severity,
                    "category": v.category,
                    "description": v.description,
                    "location": v.location,
                    "suggested_fix": v.suggested_fix,
                    "confidence": v.confidence,
                }
                for v in result.violations
            ],
        }

        needs_fix = any(
            v.severity in (ViolationSeverity.CRITICAL, ViolationSeverity.MAJOR)
            for v in result.violations
        )
        if needs_fix:
            fixed = await service.auto_fix(project_id, chapter_text, result.violations, user_id)
            if fixed:
                report["auto_fix_applied"] = True
                return fixed, report

        report["auto_fix_applied"] = False
        return chapter_text, report

    async def _run_optimizer(
        self,
        chapter_content: str,
        *,
        user_id: int,
        project_id: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        prompt_map = {
            "dialogue": "optimize_dialogue",
            "environment": "optimize_environment",
            "psychology": "optimize_psychology",
            "rhythm": "optimize_rhythm",
        }

        optimized_content = chapter_content
        notes = []
        for dimension, prompt_name in prompt_map.items():
            prompt = await self.prompt_service.get_prompt(prompt_name)
            if not prompt:
                logger.warning("缺少优化提示词 %s，跳过 %s 维度", prompt_name, dimension)
                continue

            optimize_input = {
                "original_content": optimized_content,
                "additional_notes": "在不改变剧情走向的前提下优化该维度。",
            }
            try:
                response = await self.llm_service.get_llm_response(
                    system_prompt=prompt,
                    conversation_history=[{"role": "user", "content": json.dumps(optimize_input, ensure_ascii=False)}],
                    temperature=0.7,
                    user_id=user_id,
                    timeout=600.0,
                    project_id=project_id,
                )
                cleaned = remove_think_tags(response)
                normalized = unwrap_markdown_json(cleaned)
                try:
                    parsed = json.loads(normalized)
                    optimized_content = parsed.get("optimized_content", cleaned)
                    notes.append(
                        {
                            "dimension": dimension,
                            "notes": parsed.get("optimization_notes", "优化完成"),
                        }
                    )
                except json.JSONDecodeError:
                    optimized_content = cleaned
                    notes.append({"dimension": dimension, "notes": "优化完成（响应格式非标准JSON）"})
            except Exception as exc:
                logger.warning("优化维度 %s 失败: %s", dimension, exc)

        return optimized_content, {"steps": notes}

    async def _run_enrichment(
        self,
        chapter_content: str,
        *,
        user_id: int,
        target_word_count: int = 3000,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        service = EnrichmentService(self.session, self.llm_service)
        result = await service.check_and_enrich(
            chapter_text=chapter_content,
            target_word_count=target_word_count,
            user_id=user_id,
        )
        if not result:
            return chapter_content, None

        return result.enriched_content, {
            "original_word_count": result.original_word_count,
            "enriched_word_count": result.enriched_word_count,
            "enrichment_ratio": result.enrichment_ratio,
            "enrichment_type": result.enrichment_type,
        }

    @staticmethod
    def _build_stage_flags(config: PipelineConfig) -> Dict[str, bool]:
        return {
            "preview": config.enable_preview,
            "optimizer": config.enable_optimizer,
            "consistency": config.enable_consistency,
            "enrichment": config.enable_enrichment,
            "constitution": config.enable_constitution,
            "persona": config.enable_persona,
            "six_dimension": config.enable_six_dimension,
            "reader_sim": config.enable_reader_sim,
            "self_critique": config.enable_self_critique,
            "memory": config.enable_memory,
            "rag": config.enable_rag,
            "rag_mode": config.rag_mode == "two_stage",
        }

    @staticmethod
    def _format_filtered_context(filtered: FilteredContext) -> Optional[str]:
        if not filtered:
            return None

        sections = []
        if filtered.plot_fuel:
            sections.append("## 情节燃料\n" + "\n".join(f"- {item}" for item in filtered.plot_fuel))
        if filtered.character_info:
            sections.append("## 人物维度\n" + "\n".join(f"- {item}" for item in filtered.character_info))
        if filtered.world_fragments:
            sections.append("## 世界碎片\n" + "\n".join(f"- {item}" for item in filtered.world_fragments))
        if filtered.narrative_techniques:
            sections.append("## 叙事技法\n" + "\n".join(f"- {item}" for item in filtered.narrative_techniques))
        if filtered.warnings:
            sections.append("## 冲突警告\n" + "\n".join(f"- {item}" for item in filtered.warnings))

        if not sections:
            return "（未检索到有效上下文）"

        return "\n\n".join(sections)


__all__ = ["PipelineOrchestrator", "PipelineConfig"]
