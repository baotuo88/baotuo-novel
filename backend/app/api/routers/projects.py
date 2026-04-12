# AIMETA P=项目资源API_宪法人格记忆等|R=项目资源管理|NR=不含生成逻辑|E=route:GET_PUT_/api/projects/*|X=http|A=资源接口|D=fastapi,sqlalchemy|S=db|RD=./README.ai
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...models.novel import Chapter
from ...schemas.user import UserInDB
from ...services.constitution_service import ConstitutionService
from ...services.faction_service import FactionService
from ...services.llm_service import LLMService
from ...services.memory_layer_service import MemoryLayerService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...services.writer_persona_service import WriterPersonaService
from ...models.project_memory import ProjectMemory

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class PersonaPayload(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    style_tags: Optional[List[str]] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    preferences: Optional[List[str]] = None
    avoidances: Optional[List[str]] = None
    sample_sentences: Optional[List[str]] = None
    narrative_voice: Optional[str] = None
    language_style: Optional[str] = None
    pacing_style: Optional[str] = None
    emotional_tone: Optional[str] = None
    dialogue_style: Optional[str] = None
    description_style: Optional[str] = None
    personal_quirks: Optional[List[str]] = None
    is_active: Optional[bool] = None
    extra: Optional[Dict[str, Any]] = None


class ProjectMemoryPayload(BaseModel):
    global_summary: Optional[str] = None
    plot_arcs: Optional[Dict[str, Any]] = None
    story_timeline_summary: Optional[str] = None


class FactionPayload(BaseModel):
    id: Optional[int] = None
    name: str
    faction_type: Optional[str] = None
    description: Optional[str] = None
    power_level: Optional[str] = None
    territory: Optional[str] = None
    resources: Optional[List[str]] = None
    leader: Optional[str] = None
    hierarchy: Optional[Dict[str, Any]] = None
    member_count: Optional[str] = None
    goals: Optional[List[str]] = None
    current_status: Optional[str] = None
    recent_events: Optional[List[str]] = None
    culture: Optional[str] = None
    rules: Optional[List[str]] = None
    traditions: Optional[List[str]] = None
    extra: Optional[Dict[str, Any]] = None


class GraphNode(BaseModel):
    id: str
    label: str
    node_type: str
    group: str
    level: Optional[int] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    label: Optional[str] = None
    weight: float = 1.0


class WorldGraphResponse(BaseModel):
    project_id: str
    generated_at: str
    world_tree: Dict[str, Any]
    relation_graph: Dict[str, Any]
    stats: Dict[str, int]


def _model_to_dict(instance: Any) -> Optional[Dict[str, Any]]:
    if instance is None:
        return None
    return {k: v for k, v in vars(instance).items() if not k.startswith("_")}


def _short_text(value: Any, max_length: int = 72) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        return "未命名"
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def _safe_id_fragment(value: Any) -> str:
    raw = str(value or "").strip().lower()
    chars = []
    for ch in raw:
        if ch.isalnum() or ch in {"_", "-"}:
            chars.append(ch)
        elif ch in {" ", ".", ":"}:
            chars.append("-")
    normalized = "".join(chars).strip("-")
    return normalized or "item"


def _extract_names_from_list(source: Any) -> list[str]:
    if not isinstance(source, list):
        return []
    names: list[str] = []
    for item in source:
        if isinstance(item, str):
            name = item.strip()
            if name:
                names.append(name)
            continue
        if isinstance(item, dict):
            name = (
                str(item.get("name") or item.get("title") or item.get("label") or "").strip()
            )
            if name:
                names.append(name)
    return names


def _append_world_tree_nodes(
    *,
    value: Any,
    parent_id: str,
    parent_level: int,
    key_hint: Optional[str],
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    node_limit: int,
) -> None:
    if len(nodes) >= node_limit:
        return
    next_level = parent_level + 1

    if isinstance(value, dict):
        for key, child_value in value.items():
            if len(nodes) >= node_limit:
                break
            label = _short_text(key, max_length=40)
            node_id = f"{parent_id}.{_safe_id_fragment(key)}"
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=label,
                    node_type="world_key",
                    group="world",
                    level=next_level,
                    meta={"raw_key": key},
                )
            )
            edges.append(
                GraphEdge(
                    id=f"{parent_id}->{node_id}",
                    source=parent_id,
                    target=node_id,
                    relation="contains",
                )
            )
            _append_world_tree_nodes(
                value=child_value,
                parent_id=node_id,
                parent_level=next_level,
                key_hint=str(key),
                nodes=nodes,
                edges=edges,
                node_limit=node_limit,
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value, start=1):
            if len(nodes) >= node_limit:
                break
            if isinstance(item, dict):
                title = (
                    str(item.get("name") or item.get("title") or item.get("label") or "").strip()
                    or f"{key_hint or '条目'} {index}"
                )
                item_id = f"{parent_id}.item{index}"
                nodes.append(
                    GraphNode(
                        id=item_id,
                        label=_short_text(title, max_length=40),
                        node_type="world_item",
                        group="world",
                        level=next_level,
                        meta={"index": index},
                    )
                )
                edges.append(
                    GraphEdge(
                        id=f"{parent_id}->{item_id}",
                        source=parent_id,
                        target=item_id,
                        relation="includes",
                    )
                )
                _append_world_tree_nodes(
                    value=item,
                    parent_id=item_id,
                    parent_level=next_level,
                    key_hint=key_hint,
                    nodes=nodes,
                    edges=edges,
                    node_limit=node_limit,
                )
                continue

            leaf_id = f"{parent_id}.item{index}"
            nodes.append(
                GraphNode(
                    id=leaf_id,
                    label=_short_text(item, max_length=50),
                    node_type="world_leaf",
                    group="world",
                    level=next_level,
                    meta={"index": index},
                )
            )
            edges.append(
                GraphEdge(
                    id=f"{parent_id}->{leaf_id}",
                    source=parent_id,
                    target=leaf_id,
                    relation="includes",
                )
            )
        return

    leaf_id = f"{parent_id}.value"
    nodes.append(
        GraphNode(
            id=leaf_id,
            label=_short_text(value, max_length=60),
            node_type="world_value",
            group="world",
            level=next_level,
            meta={"key_hint": key_hint or ""},
        )
    )
    edges.append(
        GraphEdge(
            id=f"{parent_id}->{leaf_id}",
            source=parent_id,
            target=leaf_id,
            relation="value",
        )
    )


@router.get("/{project_id}/constitution")
async def get_constitution(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    constitution_service = ConstitutionService(session, LLMService(session), PromptService(session))
    constitution = await constitution_service.get_constitution(project_id)
    return {"project_id": project_id, "constitution": _model_to_dict(constitution)}


@router.put("/{project_id}/constitution")
async def put_constitution(
    project_id: str,
    payload: Dict[str, Any] = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    constitution_service = ConstitutionService(session, LLMService(session), PromptService(session))
    constitution = await constitution_service.create_or_update_constitution(project_id, payload)
    return {"project_id": project_id, "constitution": _model_to_dict(constitution)}


@router.get("/{project_id}/persona")
async def get_persona(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    persona_service = WriterPersonaService(session, LLMService(session), PromptService(session))
    persona = await persona_service.get_active_persona(project_id)
    return {"project_id": project_id, "persona": _model_to_dict(persona)}


@router.put("/{project_id}/persona")
async def put_persona(
    project_id: str,
    payload: PersonaPayload,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    persona_service = WriterPersonaService(session, LLMService(session), PromptService(session))
    payload_dict = payload.model_dump(exclude_unset=True)
    persona_id = payload_dict.pop("id", None)

    if persona_id:
        existing_persona = await persona_service.get_persona_by_id(persona_id)
        if not existing_persona or existing_persona.project_id != project_id:
            raise HTTPException(status_code=404, detail="Writer 人格不存在")
        persona = await persona_service.update_persona(persona_id, payload_dict)
    else:
        persona = await persona_service.create_persona(project_id, payload_dict)

    if payload.is_active:
        await persona_service.set_active_persona(project_id, persona.id)

    return {"project_id": project_id, "persona": _model_to_dict(persona)}


@router.get("/{project_id}/memory")
async def get_project_memory(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    result = await session.execute(
        select(ProjectMemory).where(ProjectMemory.project_id == project_id)
    )
    memory = result.scalars().first()
    return {"project_id": project_id, "memory": _model_to_dict(memory)}


@router.put("/{project_id}/memory")
async def put_project_memory(
    project_id: str,
    payload: ProjectMemoryPayload,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    result = await session.execute(
        select(ProjectMemory).where(ProjectMemory.project_id == project_id)
    )
    memory = result.scalars().first()
    if not memory:
        memory = ProjectMemory(project_id=project_id)
        session.add(memory)

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if hasattr(memory, key):
            setattr(memory, key, value)

    await session.commit()
    await session.refresh(memory)
    return {"project_id": project_id, "memory": _model_to_dict(memory)}


@router.get("/{project_id}/characters/state")
async def get_character_states(
    project_id: str,
    chapter_number: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    if chapter_number is None:
        result = await session.execute(
            select(Chapter.chapter_number).where(Chapter.project_id == project_id)
        )
        chapter_numbers = [row[0] for row in result.all()]
        chapter_number = max(chapter_numbers) if chapter_numbers else 0

    memory_service = MemoryLayerService(session, LLMService(session), PromptService(session))
    states = await memory_service.get_all_character_states(project_id, chapter_number)
    return {
        "project_id": project_id,
        "chapter_number": chapter_number,
        "states": [_model_to_dict(state) for state in states],
    }


@router.get("/{project_id}/factions")
async def get_factions(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    faction_service = FactionService(session, PromptService(session))
    factions = await faction_service.get_factions_by_project(project_id)
    return {"project_id": project_id, "factions": [_model_to_dict(faction) for faction in factions]}


@router.get("/{project_id}/world-graph", response_model=WorldGraphResponse)
async def get_world_graph(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> WorldGraphResponse:
    """返回世界观树与人物关系图谱，可直接用于可视化渲染。"""
    novel_service = NovelService(session)
    project_schema = await novel_service.get_project_schema(project_id, current_user.id)
    blueprint = project_schema.blueprint

    raw_world_setting = blueprint.world_setting if blueprint else {}
    world_setting = raw_world_setting if isinstance(raw_world_setting, (dict, list)) else {}
    raw_characters = (blueprint.characters if blueprint else []) or []
    characters = raw_characters if isinstance(raw_characters, list) else []
    raw_relationships = (blueprint.relationships if blueprint else []) or []
    relationships = raw_relationships if isinstance(raw_relationships, list) else []

    world_nodes: list[GraphNode] = [
        GraphNode(
            id="world.root",
            label="世界观",
            node_type="world_root",
            group="world",
            level=0,
            meta={"project_title": project_schema.title},
        )
    ]
    world_edges: list[GraphEdge] = []
    _append_world_tree_nodes(
        value=world_setting,
        parent_id="world.root",
        parent_level=0,
        key_hint="world_setting",
        nodes=world_nodes,
        edges=world_edges,
        node_limit=180,
    )

    graph_nodes: dict[str, GraphNode] = {}
    graph_edges: list[GraphEdge] = []
    edge_seq = 1

    character_name_to_id: dict[str, str] = {}
    for index, character in enumerate(characters, start=1):
        raw_name = str(character.get("name") or f"角色 {index}").strip() or f"角色 {index}"
        name = _short_text(raw_name, max_length=40)
        node_id = f"char.{_safe_id_fragment(raw_name)}.{index}"
        graph_nodes[node_id] = GraphNode(
            id=node_id,
            label=name,
            node_type="character",
            group="character",
            meta={
                "identity": character.get("identity"),
                "personality": character.get("personality"),
                "goals": character.get("goals"),
            },
        )
        character_name_to_id.setdefault(raw_name, node_id)
        character_name_to_id.setdefault(name, node_id)

    faction_service = FactionService(session, PromptService(session))
    factions = await faction_service.get_factions_by_project(project_id)
    faction_relations = await faction_service.get_faction_relationships(project_id)

    faction_id_to_node: dict[int, str] = {}
    faction_name_to_node: dict[str, str] = {}
    for faction in factions:
        node_id = f"faction.{faction.id}"
        faction_name_raw = str(faction.name or "").strip()
        faction_label = _short_text(faction.name, max_length=40)
        graph_nodes[node_id] = GraphNode(
            id=node_id,
            label=faction_label,
            node_type="faction",
            group="faction",
            meta={
                "faction_type": faction.faction_type,
                "leader": faction.leader,
                "power_level": faction.power_level,
                "current_status": faction.current_status,
            },
        )
        faction_id_to_node[faction.id] = node_id
        if faction_name_raw:
            faction_name_to_node[faction_name_raw] = node_id
        faction_name_to_node[faction_label] = node_id

    world_setting_dict = world_setting if isinstance(world_setting, dict) else {}
    world_faction_names = _extract_names_from_list(world_setting_dict.get("factions"))
    for name in world_faction_names:
        if name in faction_name_to_node:
            continue
        node_id = f"faction.world.{_safe_id_fragment(name)}"
        graph_nodes[node_id] = GraphNode(
            id=node_id,
            label=_short_text(name, max_length=40),
            node_type="faction_stub",
            group="faction",
            meta={"source": "world_setting"},
        )
        faction_name_to_node[name] = node_id

    for relation in relationships:
        if not isinstance(relation, dict):
            continue
        source_name_raw = str(relation.get("character_from") or relation.get("from") or "").strip()
        target_name_raw = str(relation.get("character_to") or relation.get("to") or "").strip()
        if not source_name_raw or not target_name_raw:
            continue

        source_name = _short_text(source_name_raw, max_length=40)
        target_name = _short_text(target_name_raw, max_length=40)
        source_id = character_name_to_id.get(source_name_raw) or character_name_to_id.get(source_name)
        target_id = character_name_to_id.get(target_name_raw) or character_name_to_id.get(target_name)

        if not source_id:
            source_id = f"char.external.{_safe_id_fragment(source_name)}"
            graph_nodes[source_id] = GraphNode(
                id=source_id,
                label=source_name,
                node_type="character_external",
                group="character",
                meta={"source": "relationship_infer"},
            )
            character_name_to_id[source_name] = source_id
        if not target_id:
            target_id = f"char.external.{_safe_id_fragment(target_name)}.to"
            graph_nodes[target_id] = GraphNode(
                id=target_id,
                label=target_name,
                node_type="character_external",
                group="character",
                meta={"source": "relationship_infer"},
            )
            character_name_to_id[target_name] = target_id

        relation_type = (
            str(relation.get("relationship_type") or "").strip()
            or str(relation.get("type") or "").strip()
            or str(relation.get("description") or "").strip()
            or "角色关系"
        )
        graph_edges.append(
            GraphEdge(
                id=f"edge.{edge_seq}",
                source=source_id,
                target=target_id,
                relation="character_relationship",
                label=_short_text(relation_type, max_length=36),
                weight=1.0,
            )
        )
        edge_seq += 1

    for relation in faction_relations:
        source_id = faction_id_to_node.get(relation.faction_from_id)
        target_id = faction_id_to_node.get(relation.faction_to_id)
        if not source_id or not target_id:
            continue
        relation_label = relation.relationship_type or "势力关系"
        graph_edges.append(
            GraphEdge(
                id=f"edge.{edge_seq}",
                source=source_id,
                target=target_id,
                relation="faction_relationship",
                label=_short_text(relation_label, max_length=30),
                weight=float(relation.strength or 5) / 10.0,
            )
        )
        edge_seq += 1

    for faction in factions:
        if not faction.leader:
            continue
        leader_name = _short_text(faction.leader, max_length=40)
        leader_id = character_name_to_id.get(leader_name)
        faction_node_id = faction_id_to_node.get(faction.id)
        if leader_id and faction_node_id:
            graph_edges.append(
                GraphEdge(
                    id=f"edge.{edge_seq}",
                    source=leader_id,
                    target=faction_node_id,
                    relation="leader_of",
                    label="领袖",
                    weight=1.0,
                )
            )
            edge_seq += 1

    for index, character in enumerate(characters, start=1):
        character_name = _short_text(character.get("name") or f"角色 {index}", max_length=40)
        character_node = character_name_to_id.get(character_name)
        if not character_node:
            continue
        affinity_values: list[str] = []
        for key in ("affiliation", "faction", "camp", "organization", "identity"):
            value = character.get(key)
            if isinstance(value, str) and value.strip():
                affinity_values.append(value.strip())
        for value in affinity_values:
            for faction_name, faction_node in faction_name_to_node.items():
                if faction_name and faction_name in value:
                    graph_edges.append(
                        GraphEdge(
                            id=f"edge.{edge_seq}",
                            source=character_node,
                            target=faction_node,
                            relation="affiliated_with",
                            label="隶属",
                            weight=0.8,
                        )
                    )
                    edge_seq += 1
                    break

    relation_nodes = list(graph_nodes.values())
    stats = {
        "world_tree_nodes": len(world_nodes),
        "world_tree_edges": len(world_edges),
        "relation_nodes": len(relation_nodes),
        "relation_edges": len(graph_edges),
        "character_count": len([item for item in relation_nodes if item.group == "character"]),
        "faction_count": len([item for item in relation_nodes if item.group == "faction"]),
    }

    return WorldGraphResponse(
        project_id=project_id,
        generated_at=datetime.utcnow().isoformat(),
        world_tree={
            "root_id": "world.root",
            "nodes": [node.model_dump() for node in world_nodes],
            "edges": [edge.model_dump() for edge in world_edges],
        },
        relation_graph={
            "nodes": [node.model_dump() for node in relation_nodes],
            "edges": [edge.model_dump() for edge in graph_edges],
        },
        stats=stats,
    )


@router.put("/{project_id}/factions")
async def put_factions(
    project_id: str,
    payload: List[FactionPayload] = Body(...),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, Any]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    faction_service = FactionService(session, PromptService(session))
    saved = []
    for faction_payload in payload:
        data = faction_payload.model_dump(exclude_unset=True)
        faction_id = data.pop("id", None)
        if faction_id:
            existing = await faction_service.get_faction(faction_id)
            if not existing or existing.project_id != project_id:
                continue
            faction = await faction_service.update_faction(faction_id, data)
            if faction:
                saved.append(faction)
        else:
            saved.append(await faction_service.create_faction(project_id, data))

    return {"project_id": project_id, "factions": [_model_to_dict(faction) for faction in saved]}
