# AIMETA P=项目备份恢复服务_项目结构导出导入|R=项目全量备份_新项目导入_原项目恢复|NR=不含HTTP路由|E=ProjectBackupService|X=internal|A=服务类|D=sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.faction import Faction, FactionRelationship
from ..models.foreshadowing import Foreshadowing
from ..models.memory_layer import TimelineEvent
from ..models.novel import (
    BlueprintCharacter,
    BlueprintRelationship,
    Chapter,
    ChapterEvaluation,
    ChapterOutline,
    ChapterVersion,
    NovelBlueprint,
    NovelConversation,
    NovelProject,
)
from ..models.project_memory import ProjectMemory
from .novel_service import NovelService


class ProjectBackupService:
    SCHEMA_VERSION = "baotuo-backup-v1"

    def __init__(self, session: AsyncSession):
        self.session = session
        self.novel_service = NovelService(session)

    async def export_project_backup(self, *, project_id: str, user_id: int) -> Dict[str, Any]:
        await self.novel_service.ensure_project_owner(project_id, user_id)
        project = await self._load_project(project_id)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

        memory = (
            await self.session.execute(
                select(ProjectMemory).where(ProjectMemory.project_id == project_id)
            )
        ).scalars().first()
        timeline_rows = (
            await self.session.execute(
                select(TimelineEvent)
                .where(TimelineEvent.project_id == project_id)
                .order_by(TimelineEvent.chapter_number.asc(), TimelineEvent.id.asc())
            )
        ).scalars().all()
        factions = (
            await self.session.execute(
                select(Faction).where(Faction.project_id == project_id).order_by(Faction.id.asc())
            )
        ).scalars().all()
        faction_relationships = (
            await self.session.execute(
                select(FactionRelationship)
                .where(FactionRelationship.project_id == project_id)
                .order_by(FactionRelationship.id.asc())
            )
        ).scalars().all()
        foreshadowings = (
            await self.session.execute(
                select(Foreshadowing)
                .where(Foreshadowing.project_id == project_id)
                .order_by(Foreshadowing.chapter_number.asc(), Foreshadowing.id.asc())
            )
        ).scalars().all()

        outline_map: Dict[int, ChapterOutline] = {
            int(item.chapter_number): item
            for item in sorted(project.outlines or [], key=lambda row: row.chapter_number)
        }
        chapters_payload: List[Dict[str, Any]] = []
        for chapter in sorted(project.chapters or [], key=lambda row: row.chapter_number):
            chapter_number = int(chapter.chapter_number or 0)
            versions = sorted(chapter.versions or [], key=lambda row: row.created_at or datetime.min)
            version_id_to_index = {int(item.id): idx for idx, item in enumerate(versions)}
            selected_index = (
                version_id_to_index.get(int(chapter.selected_version_id))
                if chapter.selected_version_id is not None
                else None
            )
            chapters_payload.append(
                {
                    "chapter_number": chapter_number,
                    "outline": {
                        "title": (outline_map.get(chapter_number).title if outline_map.get(chapter_number) else f"第{chapter_number}章"),
                        "summary": outline_map.get(chapter_number).summary if outline_map.get(chapter_number) else "",
                        "metadata": outline_map.get(chapter_number).metadata if outline_map.get(chapter_number) else None,
                    },
                    "real_summary": chapter.real_summary,
                    "status": chapter.status,
                    "word_count": int(chapter.word_count or 0),
                    "selected_version_index": selected_index,
                    "versions": [
                        {
                            "version_label": item.version_label,
                            "provider": item.provider,
                            "content": item.content,
                            "metadata": item.metadata if isinstance(item.metadata, dict) else None,
                        }
                        for item in versions
                    ],
                    "evaluations": [
                        {
                            "decision": item.decision,
                            "feedback": item.feedback,
                            "score": item.score,
                            "version_index": (
                                version_id_to_index.get(int(item.version_id))
                                if item.version_id is not None
                                else None
                            ),
                        }
                        for item in sorted(chapter.evaluations or [], key=lambda row: row.created_at or datetime.min)
                    ],
                }
            )

        backup = {
            "meta": {
                "schema_version": self.SCHEMA_VERSION,
                "exported_at": datetime.utcnow().isoformat(),
                "source_project_id": project.id,
                "title": project.title,
            },
            "project": {
                "title": project.title,
                "initial_prompt": project.initial_prompt,
                "status": project.status,
            },
            "blueprint": {
                "title": project.blueprint.title if project.blueprint else None,
                "target_audience": project.blueprint.target_audience if project.blueprint else None,
                "genre": project.blueprint.genre if project.blueprint else None,
                "style": project.blueprint.style if project.blueprint else None,
                "tone": project.blueprint.tone if project.blueprint else None,
                "one_sentence_summary": project.blueprint.one_sentence_summary if project.blueprint else None,
                "full_synopsis": project.blueprint.full_synopsis if project.blueprint else None,
                "world_setting": project.blueprint.world_setting if project.blueprint else {},
                "characters": [
                    {
                        "name": item.name,
                        "identity": item.identity,
                        "personality": item.personality,
                        "goals": item.goals,
                        "abilities": item.abilities,
                        "relationship_to_protagonist": item.relationship_to_protagonist,
                        "extra": item.extra if isinstance(item.extra, dict) else None,
                        "position": int(item.position or 0),
                    }
                    for item in sorted(project.characters or [], key=lambda row: row.position)
                ],
                "relationships": [
                    {
                        "character_from": item.character_from,
                        "character_to": item.character_to,
                        "description": item.description,
                        "position": int(item.position or 0),
                    }
                    for item in sorted(project.relationships_ or [], key=lambda row: row.position)
                ],
            },
            "conversations": [
                {
                    "seq": int(item.seq or 0),
                    "role": item.role,
                    "content": item.content,
                    "metadata": item.metadata if isinstance(item.metadata, dict) else None,
                }
                for item in sorted(project.conversations or [], key=lambda row: row.seq)
            ],
            "chapters": chapters_payload,
            "project_memory": {
                "global_summary": memory.global_summary if memory else None,
                "plot_arcs": memory.plot_arcs if memory and isinstance(memory.plot_arcs, dict) else {},
                "story_timeline_summary": memory.story_timeline_summary if memory else None,
                "last_updated_chapter": int(memory.last_updated_chapter or 0) if memory else 0,
                "version": int(memory.version or 1) if memory else 1,
                "extra": memory.extra if memory and isinstance(memory.extra, dict) else {},
            },
            "timeline_events": [
                {
                    "chapter_number": int(item.chapter_number or 0),
                    "story_time": item.story_time,
                    "story_date": item.story_date,
                    "time_elapsed": item.time_elapsed,
                    "event_type": item.event_type,
                    "event_title": item.event_title,
                    "event_description": item.event_description,
                    "involved_characters": item.involved_characters if isinstance(item.involved_characters, list) else [],
                    "location": item.location,
                    "importance": int(item.importance or 5),
                    "is_turning_point": bool(item.is_turning_point),
                    "extra": item.extra if isinstance(item.extra, dict) else {},
                }
                for item in timeline_rows
            ],
            "factions": [
                {
                    "id": int(item.id),
                    "name": item.name,
                    "faction_type": item.faction_type,
                    "description": item.description,
                    "power_level": item.power_level,
                    "territory": item.territory,
                    "resources": item.resources if isinstance(item.resources, list) else [],
                    "leader": item.leader,
                    "hierarchy": item.hierarchy if isinstance(item.hierarchy, dict) else None,
                    "member_count": item.member_count,
                    "goals": item.goals if isinstance(item.goals, list) else [],
                    "current_status": item.current_status,
                    "recent_events": item.recent_events if isinstance(item.recent_events, list) else [],
                    "culture": item.culture,
                    "rules": item.rules if isinstance(item.rules, list) else [],
                    "traditions": item.traditions if isinstance(item.traditions, list) else [],
                    "extra": item.extra if isinstance(item.extra, dict) else None,
                }
                for item in factions
            ],
            "faction_relationships": [
                {
                    "faction_from_id": int(item.faction_from_id),
                    "faction_to_id": int(item.faction_to_id),
                    "relationship_type": item.relationship_type,
                    "strength": item.strength,
                    "description": item.description,
                    "reason": item.reason,
                }
                for item in faction_relationships
            ],
            "foreshadowings": [
                {
                    "chapter_number": int(item.chapter_number or 0),
                    "content": item.content,
                    "type": item.type,
                    "keywords": item.keywords if isinstance(item.keywords, list) else [],
                    "status": item.status,
                    "resolved_chapter_number": item.resolved_chapter_number,
                    "name": item.name,
                    "target_reveal_chapter": item.target_reveal_chapter,
                    "reveal_method": item.reveal_method,
                    "reveal_impact": item.reveal_impact,
                    "related_characters": item.related_characters if isinstance(item.related_characters, list) else [],
                    "related_plots": item.related_plots if isinstance(item.related_plots, list) else [],
                    "related_foreshadowings": item.related_foreshadowings if isinstance(item.related_foreshadowings, list) else [],
                    "importance": item.importance,
                    "urgency": item.urgency,
                    "is_manual": bool(item.is_manual),
                    "ai_confidence": item.ai_confidence,
                    "author_note": item.author_note,
                }
                for item in foreshadowings
            ],
        }
        return backup

    async def import_backup_as_new_project(self, *, user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize_backup_payload(payload)
        project_meta = normalized.get("project") if isinstance(normalized.get("project"), dict) else {}
        project_title = str(project_meta.get("title") or "恢复项目").strip() or "恢复项目"
        initial_prompt = str(project_meta.get("initial_prompt") or "通过备份导入").strip() or "通过备份导入"
        project = await self.novel_service.create_project(
            user_id=user_id,
            title=project_title,
            initial_prompt=initial_prompt,
        )
        stats = await self.restore_backup_to_project(
            project_id=project.id,
            user_id=user_id,
            payload=normalized,
        )
        return {
            "project_id": project.id,
            "title": project.title,
            "stats": stats,
        }

    async def restore_backup_to_project(
        self,
        *,
        project_id: str,
        user_id: int,
        payload: Dict[str, Any],
    ) -> Dict[str, int]:
        normalized = self._normalize_backup_payload(payload)
        project = await self.novel_service.ensure_project_owner(project_id, user_id)

        project_meta = normalized.get("project") if isinstance(normalized.get("project"), dict) else {}
        project_title = str(project_meta.get("title") or "").strip()
        if project_title:
            project.title = project_title
        initial_prompt = project_meta.get("initial_prompt")
        project.initial_prompt = str(initial_prompt) if initial_prompt is not None else project.initial_prompt
        status_value = str(project_meta.get("status") or "").strip()
        if status_value:
            project.status = status_value

        await self._clear_project_related_data(project_id)
        stats = await self._apply_backup_data(project_id, normalized)
        await self.session.commit()
        return stats

    async def _load_project(self, project_id: str) -> Optional[NovelProject]:
        stmt = (
            select(NovelProject)
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.conversations),
                selectinload(NovelProject.characters),
                selectinload(NovelProject.relationships_),
                selectinload(NovelProject.outlines),
                selectinload(NovelProject.chapters).selectinload(Chapter.versions),
                selectinload(NovelProject.chapters).selectinload(Chapter.evaluations),
            )
            .where(NovelProject.id == project_id)
        )
        return (await self.session.execute(stmt)).scalars().first()

    def _normalize_backup_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="备份数据格式错误")
        raw = payload.get("backup") if isinstance(payload.get("backup"), dict) else payload
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="备份数据格式错误")
        meta = raw.get("meta")
        if isinstance(meta, dict):
            version = str(meta.get("schema_version") or "").strip()
            if version and version != self.SCHEMA_VERSION:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的备份版本: {version}，当前仅支持 {self.SCHEMA_VERSION}",
                )
        return raw

    async def _clear_project_related_data(self, project_id: str) -> None:
        chapter_ids = (
            await self.session.execute(
                select(Chapter.id).where(Chapter.project_id == project_id)
            )
        ).scalars().all()
        chapter_id_list = [int(item) for item in chapter_ids]

        if chapter_id_list:
            await self.session.execute(delete(Foreshadowing).where(Foreshadowing.chapter_id.in_(chapter_id_list)))
            await self.session.execute(delete(ChapterEvaluation).where(ChapterEvaluation.chapter_id.in_(chapter_id_list)))
            await self.session.execute(delete(ChapterVersion).where(ChapterVersion.chapter_id.in_(chapter_id_list)))
        await self.session.execute(delete(Foreshadowing).where(Foreshadowing.project_id == project_id))
        await self.session.execute(delete(FactionRelationship).where(FactionRelationship.project_id == project_id))
        await self.session.execute(delete(Faction).where(Faction.project_id == project_id))
        await self.session.execute(delete(TimelineEvent).where(TimelineEvent.project_id == project_id))
        await self.session.execute(delete(Chapter).where(Chapter.project_id == project_id))
        await self.session.execute(delete(ChapterOutline).where(ChapterOutline.project_id == project_id))
        await self.session.execute(delete(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id))
        await self.session.execute(delete(BlueprintRelationship).where(BlueprintRelationship.project_id == project_id))
        await self.session.execute(delete(NovelConversation).where(NovelConversation.project_id == project_id))
        await self.session.execute(delete(NovelBlueprint).where(NovelBlueprint.project_id == project_id))

    async def _apply_backup_data(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, int]:
        blueprint_data = payload.get("blueprint") if isinstance(payload.get("blueprint"), dict) else {}
        conversations = payload.get("conversations") if isinstance(payload.get("conversations"), list) else []
        chapters = payload.get("chapters") if isinstance(payload.get("chapters"), list) else []
        timeline_events = payload.get("timeline_events") if isinstance(payload.get("timeline_events"), list) else []
        factions = payload.get("factions") if isinstance(payload.get("factions"), list) else []
        faction_relationships = payload.get("faction_relationships") if isinstance(payload.get("faction_relationships"), list) else []
        foreshadowings = payload.get("foreshadowings") if isinstance(payload.get("foreshadowings"), list) else []
        memory_data = payload.get("project_memory") if isinstance(payload.get("project_memory"), dict) else {}

        blueprint = NovelBlueprint(
            project_id=project_id,
            title=blueprint_data.get("title"),
            target_audience=blueprint_data.get("target_audience"),
            genre=blueprint_data.get("genre"),
            style=blueprint_data.get("style"),
            tone=blueprint_data.get("tone"),
            one_sentence_summary=blueprint_data.get("one_sentence_summary"),
            full_synopsis=blueprint_data.get("full_synopsis"),
            world_setting=blueprint_data.get("world_setting") if isinstance(blueprint_data.get("world_setting"), dict) else {},
        )
        self.session.add(blueprint)

        for item in sorted(conversations, key=lambda row: int(row.get("seq", 0)) if isinstance(row, dict) else 0):
            if not isinstance(item, dict):
                continue
            self.session.add(
                NovelConversation(
                    project_id=project_id,
                    seq=max(1, int(item.get("seq") or 1)),
                    role=str(item.get("role") or "user"),
                    content=str(item.get("content") or ""),
                    metadata_=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
                )
            )

        for item in sorted(
            blueprint_data.get("characters") if isinstance(blueprint_data.get("characters"), list) else [],
            key=lambda row: int(row.get("position", 0)) if isinstance(row, dict) else 0,
        ):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            self.session.add(
                BlueprintCharacter(
                    project_id=project_id,
                    name=name,
                    identity=item.get("identity"),
                    personality=item.get("personality"),
                    goals=item.get("goals"),
                    abilities=item.get("abilities"),
                    relationship_to_protagonist=item.get("relationship_to_protagonist"),
                    extra=item.get("extra") if isinstance(item.get("extra"), dict) else None,
                    position=max(0, int(item.get("position") or 0)),
                )
            )

        for item in sorted(
            blueprint_data.get("relationships") if isinstance(blueprint_data.get("relationships"), list) else [],
            key=lambda row: int(row.get("position", 0)) if isinstance(row, dict) else 0,
        ):
            if not isinstance(item, dict):
                continue
            char_from = str(item.get("character_from") or "").strip()
            char_to = str(item.get("character_to") or "").strip()
            if not char_from or not char_to:
                continue
            self.session.add(
                BlueprintRelationship(
                    project_id=project_id,
                    character_from=char_from,
                    character_to=char_to,
                    description=item.get("description"),
                    position=max(0, int(item.get("position") or 0)),
                )
            )

        chapter_id_by_number: Dict[int, int] = {}
        for chapter_row in sorted(chapters, key=lambda row: int(row.get("chapter_number", 0)) if isinstance(row, dict) else 0):
            if not isinstance(chapter_row, dict):
                continue
            chapter_number = int(chapter_row.get("chapter_number") or 0)
            if chapter_number <= 0:
                continue
            outline_data = chapter_row.get("outline") if isinstance(chapter_row.get("outline"), dict) else {}
            self.session.add(
                ChapterOutline(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    title=str(outline_data.get("title") or f"第{chapter_number}章"),
                    summary=str(outline_data.get("summary") or ""),
                    metadata_=outline_data.get("metadata") if isinstance(outline_data.get("metadata"), dict) else None,
                )
            )

            chapter = Chapter(
                project_id=project_id,
                chapter_number=chapter_number,
                real_summary=chapter_row.get("real_summary"),
                status=str(chapter_row.get("status") or "not_generated"),
                word_count=max(0, int(chapter_row.get("word_count") or 0)),
            )
            self.session.add(chapter)
            await self.session.flush()
            chapter_id_by_number[chapter_number] = int(chapter.id)

            versions = chapter_row.get("versions") if isinstance(chapter_row.get("versions"), list) else []
            created_versions: List[ChapterVersion] = []
            for version_item in versions:
                if not isinstance(version_item, dict):
                    continue
                content = str(version_item.get("content") or "").strip()
                if not content:
                    continue
                version = ChapterVersion(
                    chapter_id=chapter.id,
                    version_label=version_item.get("version_label"),
                    provider=version_item.get("provider"),
                    content=content,
                    metadata_=version_item.get("metadata") if isinstance(version_item.get("metadata"), dict) else None,
                )
                self.session.add(version)
                created_versions.append(version)
            await self.session.flush()

            selected_version_index = chapter_row.get("selected_version_index")
            try:
                selected_idx = int(selected_version_index) if selected_version_index is not None else None
            except (TypeError, ValueError):
                selected_idx = None
            if selected_idx is not None and 0 <= selected_idx < len(created_versions):
                chapter.selected_version_id = created_versions[selected_idx].id

            evaluations = chapter_row.get("evaluations") if isinstance(chapter_row.get("evaluations"), list) else []
            for eval_item in evaluations:
                if not isinstance(eval_item, dict):
                    continue
                version_idx_raw = eval_item.get("version_index")
                version_id = None
                try:
                    version_idx = int(version_idx_raw) if version_idx_raw is not None else None
                except (TypeError, ValueError):
                    version_idx = None
                if version_idx is not None and 0 <= version_idx < len(created_versions):
                    version_id = created_versions[version_idx].id
                self.session.add(
                    ChapterEvaluation(
                        chapter_id=chapter.id,
                        version_id=version_id,
                        decision=eval_item.get("decision"),
                        feedback=eval_item.get("feedback"),
                        score=eval_item.get("score"),
                    )
                )

        for item in timeline_events:
            if not isinstance(item, dict):
                continue
            chapter_number = int(item.get("chapter_number") or 0)
            if chapter_number <= 0:
                continue
            self.session.add(
                TimelineEvent(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    story_time=item.get("story_time"),
                    story_date=item.get("story_date"),
                    time_elapsed=item.get("time_elapsed"),
                    event_type=item.get("event_type"),
                    event_title=str(item.get("event_title") or f"第{chapter_number}章事件"),
                    event_description=item.get("event_description"),
                    involved_characters=item.get("involved_characters") if isinstance(item.get("involved_characters"), list) else [],
                    location=item.get("location"),
                    importance=max(1, min(10, int(item.get("importance") or 5))),
                    is_turning_point=bool(item.get("is_turning_point")),
                    extra=item.get("extra") if isinstance(item.get("extra"), dict) else None,
                )
            )

        faction_id_map: Dict[int, int] = {}
        for item in factions:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            faction = Faction(
                project_id=project_id,
                name=name,
                faction_type=item.get("faction_type"),
                description=item.get("description"),
                power_level=item.get("power_level"),
                territory=item.get("territory"),
                resources=item.get("resources") if isinstance(item.get("resources"), list) else [],
                leader=item.get("leader"),
                hierarchy=item.get("hierarchy") if isinstance(item.get("hierarchy"), dict) else None,
                member_count=item.get("member_count"),
                goals=item.get("goals") if isinstance(item.get("goals"), list) else [],
                current_status=item.get("current_status"),
                recent_events=item.get("recent_events") if isinstance(item.get("recent_events"), list) else [],
                culture=item.get("culture"),
                rules=item.get("rules") if isinstance(item.get("rules"), list) else [],
                traditions=item.get("traditions") if isinstance(item.get("traditions"), list) else [],
                extra=item.get("extra") if isinstance(item.get("extra"), dict) else None,
            )
            self.session.add(faction)
            await self.session.flush()
            old_id = item.get("id")
            try:
                if old_id is not None:
                    faction_id_map[int(old_id)] = int(faction.id)
            except (TypeError, ValueError):
                pass

        for item in faction_relationships:
            if not isinstance(item, dict):
                continue
            try:
                old_from = int(item.get("faction_from_id"))
                old_to = int(item.get("faction_to_id"))
            except (TypeError, ValueError):
                continue
            new_from = faction_id_map.get(old_from)
            new_to = faction_id_map.get(old_to)
            if not new_from or not new_to:
                continue
            self.session.add(
                FactionRelationship(
                    project_id=project_id,
                    faction_from_id=new_from,
                    faction_to_id=new_to,
                    relationship_type=str(item.get("relationship_type") or "neutral"),
                    strength=item.get("strength"),
                    description=item.get("description"),
                    reason=item.get("reason"),
                )
            )

        for item in foreshadowings:
            if not isinstance(item, dict):
                continue
            chapter_number = int(item.get("chapter_number") or 0)
            chapter_id = chapter_id_by_number.get(chapter_number)
            if not chapter_id:
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            resolved_number = item.get("resolved_chapter_number")
            try:
                resolved_number_int = int(resolved_number) if resolved_number is not None else None
            except (TypeError, ValueError):
                resolved_number_int = None
            resolved_chapter_id = chapter_id_by_number.get(resolved_number_int) if resolved_number_int else None
            self.session.add(
                Foreshadowing(
                    project_id=project_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    content=content,
                    type=str(item.get("type") or "hint"),
                    keywords=item.get("keywords") if isinstance(item.get("keywords"), list) else [],
                    status=str(item.get("status") or "planted"),
                    resolved_chapter_id=resolved_chapter_id,
                    resolved_chapter_number=resolved_number_int,
                    name=item.get("name"),
                    target_reveal_chapter=item.get("target_reveal_chapter"),
                    reveal_method=item.get("reveal_method"),
                    reveal_impact=item.get("reveal_impact"),
                    related_characters=item.get("related_characters") if isinstance(item.get("related_characters"), list) else [],
                    related_plots=item.get("related_plots") if isinstance(item.get("related_plots"), list) else [],
                    related_foreshadowings=item.get("related_foreshadowings") if isinstance(item.get("related_foreshadowings"), list) else [],
                    importance=item.get("importance"),
                    urgency=item.get("urgency"),
                    is_manual=bool(item.get("is_manual")),
                    ai_confidence=item.get("ai_confidence"),
                    author_note=item.get("author_note"),
                )
            )

        memory = (
            await self.session.execute(
                select(ProjectMemory).where(ProjectMemory.project_id == project_id)
            )
        ).scalars().first()
        if not memory:
            memory = ProjectMemory(project_id=project_id)
            self.session.add(memory)
        memory.global_summary = memory_data.get("global_summary")
        memory.plot_arcs = memory_data.get("plot_arcs") if isinstance(memory_data.get("plot_arcs"), dict) else {}
        memory.story_timeline_summary = memory_data.get("story_timeline_summary")
        memory.last_updated_chapter = max(0, int(memory_data.get("last_updated_chapter") or 0))
        memory.version = max(1, int(memory_data.get("version") or 1))
        memory.extra = memory_data.get("extra") if isinstance(memory_data.get("extra"), dict) else {}

        return {
            "conversation_count": len(conversations),
            "chapter_count": len([item for item in chapters if isinstance(item, dict)]),
            "timeline_count": len([item for item in timeline_events if isinstance(item, dict)]),
            "faction_count": len([item for item in factions if isinstance(item, dict)]),
            "foreshadowing_count": len([item for item in foreshadowings if isinstance(item, dict)]),
        }
