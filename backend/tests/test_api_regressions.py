import asyncio
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.api.routers import admin, analytics, analytics_enhanced
from app.services.analytics_data_service import ProjectChapterSnapshot


def _build_app(*routers) -> FastAPI:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    return app


async def _request(app: FastAPI, method: str, path: str, **kwargs):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.request(method, path, **kwargs)


def test_admin_password_endpoint_allows_default_password_admin_to_change_password():
    app = _build_app(admin.router)

    changed = {}

    class FakeAuthService:
        async def change_password(self, username: str, old_password: str, new_password: str) -> None:
            changed["username"] = username
            changed["old_password"] = old_password
            changed["new_password"] = new_password

    async def override_current_user():
        return SimpleNamespace(
            username="root",
            is_admin=True,
            must_change_password=True,
        )

    async def override_auth_service():
        return FakeAuthService()

    app.dependency_overrides[admin.get_current_user] = override_current_user
    app.dependency_overrides[admin.get_auth_service] = override_auth_service

    response = asyncio.run(
        _request(
            app,
            "POST",
            "/api/admin/password",
            json={
                "old_password": "TestAdminPassword123!",
                "new_password": "NewSecurePassword123!",
            },
        )
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert changed == {
        "username": "root",
        "old_password": "TestAdminPassword123!",
        "new_password": "NewSecurePassword123!",
    }


def test_admin_stats_route_blocks_admin_who_must_change_password():
    app = _build_app(admin.router)

    async def override_current_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前管理员仍在使用初始密码，请先修改密码后再访问管理功能",
        )

    class DummySession:
        async def scalar(self, *_args, **_kwargs):
            raise AssertionError("stats query should not execute when admin is blocked")

        async def get(self, *_args, **_kwargs):
            raise AssertionError("stats query should not execute when admin is blocked")

    async def override_session():
        return DummySession()

    app.dependency_overrides[admin.get_current_admin] = override_current_admin
    app.dependency_overrides[admin.get_session] = override_session

    response = asyncio.run(_request(app, "GET", "/api/admin/stats"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "初始密码" in response.json()["detail"]


def test_basic_analytics_emotion_curve_uses_unified_snapshot_loader(monkeypatch):
    app = _build_app(analytics.router)

    async def override_current_user():
        return SimpleNamespace(id=7, username="alice")

    async def override_session():
        return object()

    async def fake_get_project_or_404(session, project_id, user_id, *, detail="项目不存在"):
        assert project_id == "project-1"
        assert user_id == 7
        return SimpleNamespace(title="测试项目")

    async def fake_list_project_chapter_snapshots(session, project_id, *, completed_only=False):
        assert project_id == "project-1"
        assert completed_only is False
        return [
            ProjectChapterSnapshot(
                chapter_id=1,
                chapter_number=1,
                title="开端",
                summary="主角很开心",
                content="他开心地笑了！",
                status="completed",
            ),
            ProjectChapterSnapshot(
                chapter_id=2,
                chapter_number=2,
                title="危机",
                summary="局势突然紧张",
                content="敌人突然出现，他非常害怕！",
                status="completed",
            ),
        ]

    app.dependency_overrides[analytics.get_current_user] = override_current_user
    app.dependency_overrides[analytics.get_session] = override_session
    monkeypatch.setattr(analytics, "get_project_or_404", fake_get_project_or_404)
    monkeypatch.setattr(analytics, "list_project_chapter_snapshots", fake_list_project_chapter_snapshots)

    response = asyncio.run(_request(app, "GET", "/api/analytics/project-1/emotion-curve"))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["project_id"] == "project-1"
    assert payload["project_title"] == "测试项目"
    assert payload["total_chapters"] == 2
    assert len(payload["emotion_points"]) == 2
    assert payload["average_intensity"] > 0
    assert payload["emotion_distribution"]


def test_enhanced_analytics_route_uses_fixed_path_and_returns_points(monkeypatch):
    app = _build_app(analytics_enhanced.router)

    async def override_current_user():
        return SimpleNamespace(id=9, username="bob")

    async def override_session():
        return object()

    async def fake_get_project_or_404(session, project_id, user_id, *, detail="项目不存在或无权访问"):
        assert project_id == "project-2"
        assert user_id == 9
        return SimpleNamespace(id=project_id, title="增强项目")

    async def fake_list_project_chapter_snapshots(session, project_id, *, completed_only=False):
        assert project_id == "project-2"
        assert completed_only is True
        return [
            ProjectChapterSnapshot(
                chapter_id=11,
                chapter_number=3,
                title="转折",
                summary="剧情急转直下",
                content="所有人都震惊了。",
                status="completed",
            )
        ]

    async def fake_get_cache(_key):
        return None

    async def fake_set_cache(_key, _value, expire):
        assert expire == 86400

    fake_cache = SimpleNamespace(get=fake_get_cache, set=fake_set_cache)

    def fake_analyze_multidimensional_emotion(*, content, summary, chapter_number):
        assert content == "所有人都震惊了。"
        assert summary == "剧情急转直下"
        assert chapter_number == 3
        return {
            "primary_emotion": "surprise",
            "primary_intensity": 8.5,
            "secondary_emotions": [["fear", 4.2]],
            "narrative_phase": "climax",
            "pace": "fast",
            "is_turning_point": True,
            "turning_point_type": "revelation",
            "description": "关键真相揭晓带来强烈震惊",
        }

    app.dependency_overrides[analytics_enhanced.get_current_user] = override_current_user
    app.dependency_overrides[analytics_enhanced.get_session] = override_session
    monkeypatch.setattr(analytics_enhanced, "get_project_or_404", fake_get_project_or_404)
    monkeypatch.setattr(analytics_enhanced, "list_project_chapter_snapshots", fake_list_project_chapter_snapshots)
    monkeypatch.setattr(analytics_enhanced, "CacheService", lambda: fake_cache)
    monkeypatch.setattr(analytics_enhanced, "analyze_multidimensional_emotion", fake_analyze_multidimensional_emotion)

    ok_response = asyncio.run(
        _request(app, "GET", "/api/analytics/enhanced/projects/project-2/emotion-curve-enhanced")
    )
    wrong_response = asyncio.run(
        _request(app, "GET", "/enhanced/api/analytics/projects/project-2/emotion-curve-enhanced")
    )

    assert ok_response.status_code == status.HTTP_200_OK
    assert wrong_response.status_code == status.HTTP_404_NOT_FOUND

    payload = ok_response.json()
    assert len(payload) == 1
    assert payload[0]["chapter_number"] == 3
    assert payload[0]["primary_emotion"] == "surprise"


def test_comprehensive_analysis_includes_quality_foreshadowings_and_actions(monkeypatch):
    app = _build_app(analytics_enhanced.router)

    async def override_current_user():
        return SimpleNamespace(id=12, username="carol")

    async def override_session():
        return object()

    async def fake_get_enhanced_emotion_curve(*_args, **_kwargs):
        return [
            analytics_enhanced.MultidimensionalEmotionPoint(
                chapter_number=5,
                chapter_id="c-5",
                title="风暴前夜",
                primary_emotion="fear",
                primary_intensity=7.8,
                secondary_emotions=[("anticipation", 4.5)],
                narrative_phase="rising_action",
                pace="fast",
                is_turning_point=True,
                turning_point_type="reversal",
                description="危机正在逼近",
            )
        ]

    async def fake_get_story_trajectory(*_args, **_kwargs):
        return analytics_enhanced.StoryTrajectoryResponse(
            project_id="project-3",
            project_title="综合诊断项目",
            shape="man_in_hole",
            shape_confidence=0.81,
            total_chapters=5,
            avg_intensity=6.3,
            intensity_range=(2.1, 8.2),
            volatility=1.7,
            peak_chapters=[5],
            valley_chapters=[2],
            turning_points=[5],
            description="先抑后扬，临近关键转折。",
            recommendations=["保持高潮后的余波处理。"],
        )

    async def fake_get_creative_guidance(*_args, **_kwargs):
        return analytics_enhanced.CreativeGuidanceResponse(
            project_id="project-3",
            project_title="综合诊断项目",
            current_chapter=5,
            overall_assessment="整体张力良好，但仍有伏笔压力。",
            strengths=["转折明确"],
            weaknesses=["未回收伏笔较多"],
            guidance_items=[
                analytics_enhanced.GuidanceItem(
                    type="plot_development",
                    priority="high",
                    title="尽快回收主线伏笔",
                    description="把早期埋设的信息在后续两章内兑现。",
                    specific_suggestions=["优先处理主角身世相关线索"],
                    affected_chapters=[6, 7],
                    examples=[],
                )
            ],
            next_chapter_suggestions=["让角色对真相做出第一次回应"],
            long_term_planning=["在终局前完成主要伏笔闭环"],
        )

    async def fake_get_project_quality_dashboard(*_args, **_kwargs):
        return {
            "project_id": "project-3",
            "generated_at": "2026-04-22T10:00:00",
            "overall_score": 73.5,
            "metrics": {
                "consistency_score": 82.0,
                "foreshadowing_score": 58.0,
                "completion_score": 80.0,
                "stability_score": 90.0,
            },
            "chapter_stats": {
                "total_chapters": 5,
                "successful_chapters": 4,
                "failed_chapters": 0,
                "average_word_count": 2800,
            },
            "consistency": {
                "checked_versions": 4,
                "consistent_versions": 3,
                "violation_count": 2,
                "severity_breakdown": {"critical": 0, "major": 1, "minor": 1},
            },
            "foreshadowing": {
                "total": 6,
                "resolved": 2,
                "unresolved": 4,
                "overall_quality_score": 6.1,
            },
            "timeline": {"event_count": 8, "turning_points": 2},
            "top_risks": ["未回收伏笔数量偏高，存在剧情遗留风险。"],
            "recommendations": ["优先处理高重要度未回收伏笔，缩短未闭环周期。"],
        }

    async def fake_list_relevant_foreshadowings(*_args, **_kwargs):
        return [
            analytics_enhanced.ComprehensiveForeshadowingItem(
                id=101,
                chapter_number=2,
                content="主角母亲留下的钥匙仍未解释来源。",
                status="open",
                type="clue",
                priority_hint="high",
                keywords=["钥匙", "母亲"],
                related_characters=["主角", "母亲"],
            )
        ]

    app.dependency_overrides[analytics_enhanced.get_current_user] = override_current_user
    app.dependency_overrides[analytics_enhanced.get_session] = override_session
    monkeypatch.setattr(analytics_enhanced, "get_enhanced_emotion_curve", fake_get_enhanced_emotion_curve)
    monkeypatch.setattr(analytics_enhanced, "get_story_trajectory", fake_get_story_trajectory)
    monkeypatch.setattr(analytics_enhanced, "get_creative_guidance", fake_get_creative_guidance)
    monkeypatch.setattr(analytics_enhanced, "get_project_quality_dashboard", fake_get_project_quality_dashboard)
    monkeypatch.setattr(analytics_enhanced, "_list_relevant_foreshadowings", fake_list_relevant_foreshadowings)

    response = asyncio.run(
        _request(app, "GET", "/api/analytics/enhanced/projects/project-3/comprehensive-analysis")
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["project_id"] == "project-3"
    assert payload["quality_dashboard"]["overall_score"] == 73.5
    assert payload["foreshadowings"][0]["id"] == 101
    assert payload["focus_actions"]
    assert payload["focus_actions"][0]["anchor"]["section"] in {"foreshadowing", "quality_dashboard", "timeline", "chapters"}
    assert payload["emotion_points"][0]["is_turning_point"] is True


def test_ai_emotion_analysis_falls_back_to_basic_curve_when_llm_fails(monkeypatch):
    app = _build_app(analytics.router)

    async def override_current_user():
        return SimpleNamespace(id=5, username="eve")

    async def override_session():
        return object()

    async def fake_get_project_or_404(session, project_id, user_id, *, detail="项目不存在"):
        assert project_id == "project-fallback"
        assert user_id == 5
        return SimpleNamespace(title="回退项目")

    async def fake_list_project_chapter_snapshots(session, project_id, *, completed_only=False):
        return [
            ProjectChapterSnapshot(
                chapter_id=21,
                chapter_number=1,
                title="第一章",
                summary="平静开场",
                content="天气很好。",
                status="completed",
            )
        ]

    class FailingLLMService:
        def __init__(self, _session):
            pass

        async def get_llm_response(self, **_kwargs):
            raise RuntimeError("llm unavailable")

    async def fake_get_emotion_curve(project_id, session, current_user):
        assert project_id == "project-fallback"
        assert current_user.id == 5
        return analytics.EmotionCurveResponse(
            project_id=project_id,
            project_title="回退项目",
            total_chapters=1,
            emotion_points=[
                analytics.EmotionPoint(
                    chapter_number=1,
                    title="第一章",
                    emotion_type="平静",
                    intensity=3,
                    narrative_phase=None,
                    description="回退分析结果",
                )
            ],
            average_intensity=3.0,
            emotion_distribution={"平静": 1},
        )

    app.dependency_overrides[analytics.get_current_user] = override_current_user
    app.dependency_overrides[analytics.get_session] = override_session
    monkeypatch.setattr(analytics, "get_project_or_404", fake_get_project_or_404)
    monkeypatch.setattr(analytics, "list_project_chapter_snapshots", fake_list_project_chapter_snapshots)
    monkeypatch.setattr(analytics, "LLMService", FailingLLMService)
    monkeypatch.setattr(analytics, "get_emotion_curve", fake_get_emotion_curve)

    response = asyncio.run(_request(app, "POST", "/api/analytics/project-fallback/analyze-emotion-ai"))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["project_id"] == "project-fallback"
    assert payload["emotion_points"][0]["description"] == "回退分析结果"
    assert payload["emotion_distribution"] == {"平静": 1}


def test_enhanced_emotion_curve_returns_cached_payload_without_recomputing(monkeypatch):
    app = _build_app(analytics_enhanced.router)

    async def override_current_user():
        return SimpleNamespace(id=10, username="cache-user")

    async def override_session():
        return object()

    async def fake_get_project_or_404(session, project_id, user_id, *, detail="项目不存在或无权访问"):
        assert project_id == "project-cache"
        assert user_id == 10
        return SimpleNamespace(id=project_id, title="缓存项目")

    cached_payload = [
        {
            "chapter_number": 7,
            "chapter_id": "77",
            "title": "缓存章节",
            "primary_emotion": "joy",
            "primary_intensity": 6.5,
            "secondary_emotions": [["trust", 2.1]],
            "narrative_phase": "rising_action",
            "pace": "medium",
            "is_turning_point": False,
            "turning_point_type": None,
            "description": "从缓存返回的分析结果",
        }
    ]

    async def fake_get_cache(key):
        assert key == "emotion_curve_enhanced:project-cache"
        return cached_payload

    async def fake_set_cache(_key, _value, expire):
        raise AssertionError("cache hit should not rewrite cache")

    async def fail_list_project_chapter_snapshots(*_args, **_kwargs):
        raise AssertionError("cache hit should not load chapter snapshots")

    def fail_analyze_multidimensional_emotion(**_kwargs):
        raise AssertionError("cache hit should not recompute emotion analysis")

    fake_cache = SimpleNamespace(get=fake_get_cache, set=fake_set_cache)

    app.dependency_overrides[analytics_enhanced.get_current_user] = override_current_user
    app.dependency_overrides[analytics_enhanced.get_session] = override_session
    monkeypatch.setattr(analytics_enhanced, "get_project_or_404", fake_get_project_or_404)
    monkeypatch.setattr(analytics_enhanced, "CacheService", lambda: fake_cache)
    monkeypatch.setattr(
        analytics_enhanced,
        "list_project_chapter_snapshots",
        fail_list_project_chapter_snapshots,
    )
    monkeypatch.setattr(
        analytics_enhanced,
        "analyze_multidimensional_emotion",
        fail_analyze_multidimensional_emotion,
    )

    response = asyncio.run(
        _request(app, "GET", "/api/analytics/enhanced/projects/project-cache/emotion-curve-enhanced")
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload == cached_payload


def test_invalidate_analysis_cache_deletes_all_related_keys(monkeypatch):
    app = _build_app(analytics_enhanced.router)

    async def override_current_user():
        return SimpleNamespace(id=12, username="cache-admin")

    async def override_session():
        return object()

    async def fake_get_project_or_404(session, project_id, user_id, *, detail="项目不存在或无权访问"):
        assert project_id == "project-clear"
        assert user_id == 12
        return SimpleNamespace(id=project_id, title="清缓存项目")

    deleted_keys: list[str] = []

    async def fake_delete_cache(key):
        deleted_keys.append(key)

    fake_cache = SimpleNamespace(delete=fake_delete_cache)

    app.dependency_overrides[analytics_enhanced.get_current_user] = override_current_user
    app.dependency_overrides[analytics_enhanced.get_session] = override_session
    monkeypatch.setattr(analytics_enhanced, "get_project_or_404", fake_get_project_or_404)
    monkeypatch.setattr(analytics_enhanced, "CacheService", lambda: fake_cache)

    response = asyncio.run(
        _request(app, "POST", "/api/analytics/enhanced/projects/project-clear/invalidate-cache")
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"message": "缓存已清除", "project_id": "project-clear"}
    assert deleted_keys == [
        "emotion_curve_enhanced:project-clear",
        "story_trajectory:project-clear",
        "creative_guidance:project-clear",
    ]


def test_comprehensive_analysis_composes_emotion_trajectory_and_guidance(monkeypatch):
    app = _build_app(analytics_enhanced.router)

    async def override_current_user():
        return SimpleNamespace(id=13, username="planner")

    async def override_session():
        return object()

    async def fake_get_enhanced_emotion_curve(**kwargs):
        assert kwargs["project_id"] == "project-full"
        return [
            analytics_enhanced.MultidimensionalEmotionPoint(
                chapter_number=1,
                chapter_id="1",
                title="序章",
                primary_emotion="anticipation",
                primary_intensity=6.0,
                secondary_emotions=[("trust", 2.0)],
                narrative_phase="exposition",
                pace="medium",
                is_turning_point=False,
                turning_point_type=None,
                description="情绪逐渐升温",
            )
        ]

    async def fake_get_story_trajectory(**kwargs):
        assert kwargs["project_id"] == "project-full"
        return analytics_enhanced.StoryTrajectoryResponse(
            project_id="project-full",
            project_title="综合分析项目",
            shape="man_in_hole",
            shape_confidence=0.88,
            total_chapters=1,
            avg_intensity=6.0,
            intensity_range=(6.0, 6.0),
            volatility=0.0,
            peak_chapters=[1],
            valley_chapters=[],
            turning_points=[],
            description="单章样本",
            recommendations=["继续推进冲突"],
        )

    async def fake_get_creative_guidance(**kwargs):
        assert kwargs["project_id"] == "project-full"
        return analytics_enhanced.CreativeGuidanceResponse(
            project_id="project-full",
            project_title="综合分析项目",
            current_chapter=1,
            overall_assessment="节奏稳定",
            strengths=["开篇目标明确"],
            weaknesses=["冲突尚浅"],
            guidance_items=[],
            next_chapter_suggestions=["引入更强阻力"],
            long_term_planning=["预埋后续反转"],
        )

    async def fake_get_project_quality_dashboard(**_kwargs):
        return {
            "project_id": "project-full",
            "generated_at": "2026-04-22T10:00:00",
            "overall_score": 88.0,
            "metrics": {
                "consistency_score": 92.0,
                "foreshadowing_score": 75.0,
                "completion_score": 100.0,
                "stability_score": 100.0,
            },
            "chapter_stats": {
                "total_chapters": 1,
                "successful_chapters": 1,
                "failed_chapters": 0,
                "average_word_count": 3200,
            },
            "consistency": {
                "checked_versions": 1,
                "consistent_versions": 1,
                "violation_count": 0,
                "severity_breakdown": {"critical": 0, "major": 0, "minor": 0},
            },
            "foreshadowing": {"total": 0, "resolved": 0, "unresolved": 0, "overall_quality_score": 0.0},
            "timeline": {"event_count": 1, "turning_points": 0},
            "top_risks": [],
            "recommendations": ["继续推进冲突"],
        }

    async def fake_list_relevant_foreshadowings(*_args, **_kwargs):
        return []

    app.dependency_overrides[analytics_enhanced.get_current_user] = override_current_user
    app.dependency_overrides[analytics_enhanced.get_session] = override_session
    monkeypatch.setattr(analytics_enhanced, "get_enhanced_emotion_curve", fake_get_enhanced_emotion_curve)
    monkeypatch.setattr(analytics_enhanced, "get_story_trajectory", fake_get_story_trajectory)
    monkeypatch.setattr(analytics_enhanced, "get_creative_guidance", fake_get_creative_guidance)
    monkeypatch.setattr(analytics_enhanced, "get_project_quality_dashboard", fake_get_project_quality_dashboard)
    monkeypatch.setattr(analytics_enhanced, "_list_relevant_foreshadowings", fake_list_relevant_foreshadowings)

    response = asyncio.run(
        _request(app, "GET", "/api/analytics/enhanced/projects/project-full/comprehensive-analysis")
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["project_id"] == "project-full"
    assert payload["project_title"] == "综合分析项目"
    assert payload["trajectory"]["shape"] == "man_in_hole"
    assert payload["guidance"]["overall_assessment"] == "节奏稳定"
    assert payload["emotion_points"][0]["primary_emotion"] == "anticipation"
    assert payload["quality_dashboard"]["overall_score"] == 88.0
    assert payload["foreshadowings"] == []
