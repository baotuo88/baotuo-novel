# AIMETA P=增强分析API_多维情感和故事轨迹|R=多维情感_轨迹分析_创意指导|NR=不含基础分析|E=route:GET_/api/analytics/enhanced/*|X=http|A=多维情感_轨迹_指导|D=fastapi,redis|S=db,cache|RD=./README.ai
"""
增强的情感曲线和故事分析 API
集成多维情感分析、故事轨迹分析和创意指导系统
"""

import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...models.foreshadowing import Foreshadowing
from ...schemas.user import UserInDB
from ...services.analytics_data_service import get_project_or_404, list_project_chapter_snapshots
from ...services.emotion_analyzer_enhanced import analyze_multidimensional_emotion
from ...services.story_trajectory_analyzer import analyze_story_trajectory
from ...services.creative_guidance_system import generate_creative_guidance
from ...services.cache_service import CacheService
from .projects import get_project_quality_dashboard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics/enhanced", tags=["Analytics"])

# ==================== 数据模型 ====================

class MultidimensionalEmotionPoint(BaseModel):
    """多维情感数据点"""
    chapter_number: int
    chapter_id: str
    title: str
    
    # 主情感
    primary_emotion: str  # joy, sadness, anger, fear, surprise, anticipation, trust, neutral
    primary_intensity: float = Field(..., ge=0, le=10)
    
    # 次要情感
    secondary_emotions: List[tuple[str, float]] = []
    
    # 叙事阶段
    narrative_phase: str  # exposition, rising_action, climax, falling_action, resolution
    
    # 节奏
    pace: str  # slow, medium, fast
    
    # 转折点
    is_turning_point: bool
    turning_point_type: Optional[str] = None
    
    # 描述
    description: str


class StoryTrajectoryResponse(BaseModel):
    """故事轨迹分析响应"""
    project_id: str
    project_title: str
    
    # 轨迹形状
    shape: str  # rags_to_riches, riches_to_rags, man_in_hole, icarus, cinderella, oedipus, flat
    shape_confidence: float = Field(..., ge=0, le=1)
    
    # 统计数据
    total_chapters: int
    avg_intensity: float
    intensity_range: tuple[float, float]
    volatility: float
    
    # 关键点
    peak_chapters: List[int]
    valley_chapters: List[int]
    turning_points: List[int]
    
    # 描述和建议
    description: str
    recommendations: List[str]


class GuidanceItem(BaseModel):
    """指导项"""
    type: str  # plot_development, emotion_pacing, character_arc, conflict_escalation, etc.
    priority: str  # critical, high, medium, low
    title: str
    description: str
    specific_suggestions: List[str]
    affected_chapters: List[int]
    examples: List[str] = []


class CreativeGuidanceResponse(BaseModel):
    """创意指导响应"""
    project_id: str
    project_title: str
    current_chapter: int
    
    # 总体评估
    overall_assessment: str
    strengths: List[str]
    weaknesses: List[str]
    
    # 具体指导
    guidance_items: List[GuidanceItem]
    
    # 建议
    next_chapter_suggestions: List[str]
    long_term_planning: List[str]


class ComprehensiveActionAnchor(BaseModel):
    """综合诊断中的跳转锚点"""
    section: str
    chapter_number: Optional[int] = None
    foreshadowing_id: Optional[int] = None
    timeline_event_id: Optional[int] = None
    term: Optional[str] = None
    query: Optional[str] = None


class ComprehensiveActionItem(BaseModel):
    """综合诊断中的建议动作"""
    id: str
    title: str
    summary: str
    severity: str
    category: str
    anchor: ComprehensiveActionAnchor


class ComprehensiveForeshadowingItem(BaseModel):
    """综合诊断中展示的重点伏笔"""
    id: int
    chapter_number: int
    content: str
    status: str
    type: str
    priority_hint: str
    keywords: List[str] = []
    related_characters: List[str] = []


class ComprehensiveAnalysisResponse(BaseModel):
    """综合分析响应（包含所有分析结果）"""
    project_id: str
    project_title: str
    
    # 多维情感分析
    emotion_points: List[MultidimensionalEmotionPoint]
    
    # 故事轨迹分析
    trajectory: StoryTrajectoryResponse
    
    # 创意指导
    guidance: CreativeGuidanceResponse

    # 质量与伏笔快照
    quality_dashboard: Dict[str, Any]
    foreshadowings: List[ComprehensiveForeshadowingItem]

    # 可执行动作
    focus_actions: List[ComprehensiveActionItem]


def _normalize_foreshadowing_status(status: Optional[str]) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"resolved", "revealed", "paid_off"}:
        return "resolved"
    if normalized == "abandoned":
        return "abandoned"
    return "open"


async def _list_relevant_foreshadowings(
    session: AsyncSession,
    project_id: str,
    *,
    limit: int = 8,
) -> List[ComprehensiveForeshadowingItem]:
    rows = (
        await session.execute(
            select(Foreshadowing)
            .where(Foreshadowing.project_id == project_id)
            .order_by(Foreshadowing.chapter_number.asc(), Foreshadowing.id.asc())
        )
    ).scalars().all()

    if not rows:
        return []

    unresolved: List[ComprehensiveForeshadowingItem] = []
    resolved: List[ComprehensiveForeshadowingItem] = []
    abandoned: List[ComprehensiveForeshadowingItem] = []

    for item in rows:
        status = _normalize_foreshadowing_status(item.status)
        priority_hint = "high" if (item.importance or "").strip().lower() == "major" or int(item.urgency or 0) >= 7 else "normal"
        serialized = ComprehensiveForeshadowingItem(
            id=int(item.id),
            chapter_number=int(item.chapter_number or 0),
            content=str(item.content or ""),
            status=status,
            type=str(item.type or "unknown"),
            priority_hint=priority_hint,
            keywords=[str(keyword) for keyword in (item.keywords or []) if str(keyword).strip()],
            related_characters=[
                str(name) for name in (item.related_characters or []) if str(name).strip()
            ],
        )
        if status == "open":
            unresolved.append(serialized)
        elif status == "resolved":
            resolved.append(serialized)
        else:
            abandoned.append(serialized)

    return (unresolved + resolved + abandoned)[:limit]


def _build_focus_actions(
    trajectory: StoryTrajectoryResponse,
    guidance: CreativeGuidanceResponse,
    quality_dashboard: Dict[str, Any],
    foreshadowings: List[ComprehensiveForeshadowingItem],
) -> List[ComprehensiveActionItem]:
    actions: List[ComprehensiveActionItem] = []

    top_risks = quality_dashboard.get("top_risks") if isinstance(quality_dashboard, dict) else []
    if isinstance(top_risks, list):
        for index, item in enumerate(top_risks[:2]):
            if not isinstance(item, str) or not item.strip():
                continue
            lowered = item.lower()
            section = "quality_dashboard"
            if "伏笔" in item:
                section = "foreshadowing"
            elif "时间线" in item:
                section = "timeline"
            elif "章节" in item or "一致性" in item:
                section = "chapters"
            actions.append(
                ComprehensiveActionItem(
                    id=f"risk-{index}",
                    title="优先处理高风险项",
                    summary=item.strip(),
                    severity="high",
                    category="quality_risk",
                    anchor=ComprehensiveActionAnchor(
                        section=section,
                        query="一致性" if "一致性" in item else ("时间线" if "时间线" in item else ("伏笔" if "伏笔" in item else None)),
                    ),
                )
            )

    if trajectory.turning_points:
        actions.append(
            ComprehensiveActionItem(
                id="trajectory-turning-point",
                title="复查关键转折章节",
                summary=f"故事轨迹识别到关键转折章节：第 {trajectory.turning_points[0]} 章，可优先检查时间线与伏笔衔接。",
                severity="medium",
                category="trajectory",
                anchor=ComprehensiveActionAnchor(
                    section="timeline",
                    chapter_number=int(trajectory.turning_points[0]),
                ),
            )
        )

    for item in guidance.guidance_items[:2]:
        chapter_number = item.affected_chapters[0] if item.affected_chapters else None
        section = "chapters"
        if item.type == "emotion_pacing":
            section = "emotion_curve"
        actions.append(
            ComprehensiveActionItem(
                id=f"guidance-{item.type}-{len(actions)}",
                title=item.title,
                summary=item.description,
                severity=item.priority,
                category=item.type,
                anchor=ComprehensiveActionAnchor(
                    section=section,
                    chapter_number=chapter_number,
                    query=item.specific_suggestions[0] if item.specific_suggestions else None,
                ),
            )
        )

    for item in foreshadowings:
        if item.status != "open":
            continue
        actions.append(
            ComprehensiveActionItem(
                id=f"foreshadowing-{item.id}",
                title="处理未回收伏笔",
                summary=f"第 {item.chapter_number} 章的伏笔仍未闭环：{item.content[:72]}",
                severity="high" if item.priority_hint == "high" else "medium",
                category="foreshadowing",
                anchor=ComprehensiveActionAnchor(
                    section="foreshadowing",
                    chapter_number=item.chapter_number,
                    foreshadowing_id=item.id,
                    query=item.keywords[0] if item.keywords else None,
                ),
            )
        )
        if len(actions) >= 6:
            break

    return actions[:6]


# ==================== API 端点 ====================

@router.get(
    "/projects/{project_id}/emotion-curve-enhanced",
    response_model=List[MultidimensionalEmotionPoint],
    summary="获取增强的多维情感曲线"
)
async def get_enhanced_emotion_curve(
    project_id: str,
    use_cache: bool = Query(True, description="是否使用缓存"),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[MultidimensionalEmotionPoint]:
    """
    获取项目的多维情感曲线分析
    
    包含：
    - 8种情感类型识别
    - 主情感 + 次要情感
    - 叙事阶段检测
    - 情感节奏分析
    - 转折点检测
    """
    await get_project_or_404(session, project_id, current_user.id)
    
    # 尝试从缓存获取
    cache_service = CacheService()
    cache_key = f"emotion_curve_enhanced:{project_id}"
    
    if use_cache:
        cached = await cache_service.get(cache_key)
        if cached:
            logger.info(f"从缓存返回项目 {project_id} 的增强情感曲线")
            return [MultidimensionalEmotionPoint(**point) for point in cached]
    
    chapter_snapshots = await list_project_chapter_snapshots(session, project_id, completed_only=True)
    if not chapter_snapshots:
        return []
    
    # 对每章进行多维情感分析
    emotion_points = []
    
    for chapter in chapter_snapshots:
        if not chapter.content:
            continue
        analysis = analyze_multidimensional_emotion(
            content=chapter.content,
            summary=chapter.summary or "",
            chapter_number=chapter.chapter_number
        )

        emotion_points.append(MultidimensionalEmotionPoint(
            chapter_number=chapter.chapter_number,
            chapter_id=str(chapter.chapter_id),
            title=chapter.title,
            primary_emotion=analysis['primary_emotion'],
            primary_intensity=analysis['primary_intensity'],
            secondary_emotions=analysis['secondary_emotions'],
            narrative_phase=analysis['narrative_phase'],
            pace=analysis['pace'],
            is_turning_point=analysis['is_turning_point'],
            turning_point_type=analysis['turning_point_type'],
            description=analysis['description']
        ))
    
    # 缓存结果（24小时）
    if emotion_points:
        await cache_service.set(
            cache_key,
            [point.model_dump() for point in emotion_points],
            expire=86400
        )
    
    return emotion_points


@router.get(
    "/projects/{project_id}/story-trajectory",
    response_model=StoryTrajectoryResponse,
    summary="获取故事轨迹分析"
)
async def get_story_trajectory(
    project_id: str,
    use_cache: bool = Query(True, description="是否使用缓存"),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> StoryTrajectoryResponse:
    """
    获取故事轨迹分析
    
    包含：
    - 6种基本故事形状识别
    - 轨迹片段分析
    - 高峰/低谷/转折点识别
    - 波动性统计
    - 优化建议
    """
    project = await get_project_or_404(session, project_id, current_user.id)
    
    # 尝试从缓存获取
    cache_service = CacheService()
    cache_key = f"story_trajectory:{project_id}"
    
    if use_cache:
        cached = await cache_service.get(cache_key)
        if cached:
            logger.info(f"从缓存返回项目 {project_id} 的故事轨迹分析")
            return StoryTrajectoryResponse(**cached)
    
    # 先获取情感点数据
    emotion_points_response = await get_enhanced_emotion_curve(
        project_id=project_id,
        use_cache=use_cache,
        session=session,
        current_user=current_user
    )
    
    if not emotion_points_response:
        raise HTTPException(status_code=400, detail="项目尚无已完成的章节，无法进行轨迹分析")
    
    # 转换为分析所需的格式
    emotion_points = [
        {
            'chapter_number': point.chapter_number,
            'primary_intensity': point.primary_intensity,
            'primary_emotion': point.primary_emotion,
            'secondary_emotions': point.secondary_emotions,
            'pace': point.pace,
        }
        for point in emotion_points_response
    ]
    
    # 执行故事轨迹分析
    trajectory_result = analyze_story_trajectory(emotion_points)
    
    response = StoryTrajectoryResponse(
        project_id=project_id,
        project_title=project.title,
        shape=trajectory_result['shape'],
        shape_confidence=trajectory_result['shape_confidence'],
        total_chapters=trajectory_result['total_chapters'],
        avg_intensity=trajectory_result['avg_intensity'],
        intensity_range=trajectory_result['intensity_range'],
        volatility=trajectory_result['volatility'],
        peak_chapters=trajectory_result['peak_chapters'],
        valley_chapters=trajectory_result['valley_chapters'],
        turning_points=trajectory_result['turning_points'],
        description=trajectory_result['description'],
        recommendations=trajectory_result['recommendations']
    )
    
    # 缓存结果（24小时）
    await cache_service.set(cache_key, response.model_dump(), expire=86400)
    
    return response


@router.get(
    "/projects/{project_id}/creative-guidance",
    response_model=CreativeGuidanceResponse,
    summary="获取创意指导"
)
async def get_creative_guidance(
    project_id: str,
    use_cache: bool = Query(True, description="是否使用缓存"),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> CreativeGuidanceResponse:
    """
    获取创意指导和写作建议
    
    包含：
    - 总体评估和优劣势分析
    - 6类指导建议
    - 优先级分级
    - 下一章建议
    - 长期规划指导
    """
    project = await get_project_or_404(session, project_id, current_user.id)
    
    # 尝试从缓存获取
    cache_service = CacheService()
    cache_key = f"creative_guidance:{project_id}"
    
    if use_cache:
        cached = await cache_service.get(cache_key)
        if cached:
            logger.info(f"从缓存返回项目 {project_id} 的创意指导")
            return CreativeGuidanceResponse(**cached)
    
    # 获取情感点和轨迹分析
    emotion_points_response = await get_enhanced_emotion_curve(
        project_id=project_id,
        use_cache=use_cache,
        session=session,
        current_user=current_user
    )
    
    if not emotion_points_response:
        raise HTTPException(status_code=400, detail="项目尚无已完成的章节，无法生成指导")
    
    trajectory_response = await get_story_trajectory(
        project_id=project_id,
        use_cache=use_cache,
        session=session,
        current_user=current_user
    )
    
    # 转换为分析所需的格式
    emotion_points = [
        {
            'chapter_number': point.chapter_number,
            'primary_intensity': point.primary_intensity,
            'primary_emotion': point.primary_emotion,
            'secondary_emotions': point.secondary_emotions,
            'pace': point.pace,
        }
        for point in emotion_points_response
    ]
    
    trajectory_analysis = trajectory_response.model_dump()
    current_chapter = max(point.chapter_number for point in emotion_points_response)
    foreshadowings = await _list_relevant_foreshadowings(session, project_id)
    
    # 执行创意指导生成
    guidance_result = generate_creative_guidance(
        emotion_points=emotion_points,
        trajectory_analysis=trajectory_analysis,
        current_chapter=current_chapter,
        foreshadowings=[item.model_dump() for item in foreshadowings],
    )
    
    response = CreativeGuidanceResponse(
        project_id=project_id,
        project_title=project.title,
        current_chapter=current_chapter,
        overall_assessment=guidance_result['overall_assessment'],
        strengths=guidance_result['strengths'],
        weaknesses=guidance_result['weaknesses'],
        guidance_items=[
            GuidanceItem(**item) for item in guidance_result['guidance_items']
        ],
        next_chapter_suggestions=guidance_result['next_chapter_suggestions'],
        long_term_planning=guidance_result['long_term_planning']
    )
    
    # 缓存结果（12小时）
    await cache_service.set(cache_key, response.model_dump(), expire=43200)
    
    return response


@router.get(
    "/projects/{project_id}/comprehensive-analysis",
    response_model=ComprehensiveAnalysisResponse,
    summary="获取综合分析（包含所有分析结果）"
)
async def get_comprehensive_analysis(
    project_id: str,
    use_cache: bool = Query(True, description="是否使用缓存"),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ComprehensiveAnalysisResponse:
    """
    一次性获取所有分析结果
    
    包含：
    - 多维情感曲线
    - 故事轨迹分析
    - 创意指导
    """
    # 并行获取三个分析结果
    emotion_points = await get_enhanced_emotion_curve(
        project_id=project_id,
        use_cache=use_cache,
        session=session,
        current_user=current_user
    )
    
    trajectory = await get_story_trajectory(
        project_id=project_id,
        use_cache=use_cache,
        session=session,
        current_user=current_user
    )
    
    guidance = await get_creative_guidance(
        project_id=project_id,
        use_cache=use_cache,
        session=session,
        current_user=current_user
    )
    quality_dashboard = await get_project_quality_dashboard(
        project_id=project_id,
        session=session,
        current_user=current_user,
    )
    foreshadowings = await _list_relevant_foreshadowings(session, project_id)
    focus_actions = _build_focus_actions(
        trajectory=trajectory,
        guidance=guidance,
        quality_dashboard=quality_dashboard,
        foreshadowings=foreshadowings,
    )
    
    return ComprehensiveAnalysisResponse(
        project_id=project_id,
        project_title=trajectory.project_title,
        emotion_points=emotion_points,
        trajectory=trajectory,
        guidance=guidance,
        quality_dashboard=quality_dashboard,
        foreshadowings=foreshadowings,
        focus_actions=focus_actions,
    )


@router.post(
    "/projects/{project_id}/invalidate-cache",
    summary="清除项目的分析缓存"
)
async def invalidate_analysis_cache(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Dict[str, str]:
    """
    清除项目的所有分析缓存
    
    用于：
    - 章节更新后强制重新分析
    - 手动刷新分析结果
    """
    await get_project_or_404(session, project_id, current_user.id)
    
    # 清除所有相关缓存
    cache_service = CacheService()
    cache_keys = [
        f"emotion_curve_enhanced:{project_id}",
        f"story_trajectory:{project_id}",
        f"creative_guidance:{project_id}",
    ]
    
    for key in cache_keys:
        await cache_service.delete(key)
    
    logger.info(f"已清除项目 {project_id} 的所有分析缓存")
    
    return {"message": "缓存已清除", "project_id": project_id}
