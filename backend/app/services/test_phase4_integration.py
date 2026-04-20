# AIMETA P=第四阶段集成测试_功能验证|R=单元测试_集成测试|NR=不含生产代码|E=test_main|X=internal|A=测试函数|D=pytest|S=none|RD=./README.ai
"""
第四阶段集成测试
测试所有优化模块的功能
"""

try:
    from .prompt_templates_optimized import (
        SYSTEM_MESSAGE_NOVELIST,
        generate_chapter_prompt,
        generate_outline_prompt,
        PROMPT_TEMPLATES,
    )
    from .pacing_controller import PacingController
    from .character_knowledge_manager import (
        CharacterKnowledgeManager,
        KnowledgeType,
        AcquisitionMethod,
    )
    from .outline_rewriter import OutlineRewriter, PostProcessor
except ImportError:  # pragma: no cover - 兼容直接 python 执行
    from prompt_templates_optimized import (
        SYSTEM_MESSAGE_NOVELIST,
        generate_chapter_prompt,
        generate_outline_prompt,
        PROMPT_TEMPLATES,
    )
    from pacing_controller import PacingController
    from character_knowledge_manager import (
        CharacterKnowledgeManager,
        KnowledgeType,
        AcquisitionMethod,
    )
    from outline_rewriter import OutlineRewriter, PostProcessor


def test_prompt_templates():
    """测试 Prompt 模板系统"""
    print("="*60)
    print("测试 1: Prompt 模板系统")
    print("="*60)
    
    # 测试系统消息
    assert len(SYSTEM_MESSAGE_NOVELIST) > 0
    assert "叙事风格" in SYSTEM_MESSAGE_NOVELIST
    assert "节奏控制" in SYSTEM_MESSAGE_NOVELIST
    print("✅ 系统消息模板正常")
    
    # 测试章节生成 Prompt
    project_info = {
        'title': '测试小说',
        'genre': '玄幻',
        'style': '热血',
        'worldview': '修仙世界',
        'chapter_length': 3000,
    }
    
    character_knowledge = {
        'known_facts': ['主角是凡人', '世界有修仙者'],
        'unknown_facts': ['主角实际上是神族后裔'],
    }
    
    prompt = generate_chapter_prompt(
        project_info=project_info,
        chapter_number=1,
        outline="主角在村庄遇到修仙者",
        emotion_intensity_target=6.5,
        character_knowledge=character_knowledge,
        active_characters=['主角', '村长'],
    )
    
    assert '测试小说' in prompt
    assert '6.5/10' in prompt
    assert '主角当前已知信息' in prompt
    print("✅ 章节生成 Prompt 正常")
    
    # 测试大纲生成 Prompt
    outline_prompt = generate_outline_prompt(
        project_info=project_info,
        total_chapters=30,
        story_structure="three_act",
    )
    
    assert '30' in outline_prompt or '三十' in outline_prompt
    assert '三幕结构' in outline_prompt
    print("✅ 大纲生成 Prompt 正常")
    
    print("\n✅ Prompt 模板系统测试通过\n")


def test_pacing_controller():
    """测试节奏控制器"""
    print("="*60)
    print("测试 2: 节奏控制器")
    print("="*60)
    
    # 创建控制器
    controller = PacingController(total_chapters=30, story_structure="three_act")
    
    # 规划情绪曲线
    curve = controller.plan_emotion_curve(
        min_intensity=2.0,
        max_intensity=9.5,
        num_peaks=3,
    )
    
    assert len(curve) == 30
    print(f"✅ 成功规划 {len(curve)} 章的情绪曲线")
    
    # 检查曲线数据
    first_chapter = curve[0]
    assert 'chapter_number' in first_chapter
    assert 'emotion_intensity' in first_chapter
    assert 'narrative_phase' in first_chapter
    print("✅ 情绪曲线数据结构正确")
    
    # 获取章节节奏信息
    pacing = controller.get_chapter_pacing(15)
    assert 'pacing_advice' in pacing
    assert len(pacing['pacing_advice']) > 0
    print(f"✅ 第15章节奏建议：{len(pacing['pacing_advice'])} 条")
    
    # 验证曲线
    validation = controller.validate_curve()
    assert 'valid' in validation
    assert 'summary' in validation
    print(f"✅ 曲线验证完成，有效性：{validation['valid']}")
    
    # 测试英雄之旅结构
    hero_controller = PacingController(total_chapters=40, story_structure="hero_journey")
    hero_curve = hero_controller.plan_emotion_curve()
    assert len(hero_curve) == 40
    print("✅ 英雄之旅结构情绪曲线规划正常")
    
    print("\n✅ 节奏控制器测试通过\n")


def test_character_knowledge_manager():
    """测试主角认知管理器"""
    print("="*60)
    print("测试 3: 主角认知管理器")
    print("="*60)
    
    # 创建管理器
    manager = CharacterKnowledgeManager(protagonist_name="林枫")
    
    # 添加知识
    manager.add_knowledge(
        "world_001",
        "这个世界分为修仙界和凡人界",
        KnowledgeType.WORLD_SETTING,
        is_initially_known=True,
    )
    
    manager.add_knowledge(
        "secret_001",
        "主角实际上是神族后裔",
        KnowledgeType.PLOT_SECRET,
        is_initially_known=False,
        importance="critical",
    )
    
    known = manager.get_known_knowledge()
    unknown = manager.get_unknown_knowledge()
    
    assert len(known) == 1
    assert len(unknown) == 1
    print(f"✅ 知识管理：已知 {len(known)} 条，未知 {len(unknown)} 条")
    
    # 揭示知识
    reveal_result = manager.reveal_knowledge(
        "secret_001",
        chapter_number=15,
        method=AcquisitionMethod.INVESTIGATED,
    )
    
    assert reveal_result['already_known'] == False
    assert reveal_result['chapter'] == 15
    print("✅ 知识揭示机制正常")
    
    # 添加角色
    manager.add_character(
        "char_001",
        "苏婉儿",
        "ally",
        relationship="青梅竹马",
        basic_info="温柔善良的女子",
        appearance_priority=1,
    )
    
    manager.add_character(
        "char_002",
        "剑圣",
        "mentor",
        relationship="师父",
        appearance_priority=2,
    )
    
    # 提及角色
    mention_result = manager.mention_character("char_002", 3)
    assert 'character_name' in mention_result
    print("✅ 角色提及机制正常")
    
    # 引入角色
    intro_result = manager.introduce_character("char_001", 1)
    assert intro_result['already_introduced'] == False
    assert intro_result['character_name'] == "苏婉儿"
    print("✅ 角色引入机制正常")
    
    # 获取已出场角色
    introduced = manager.get_introduced_characters()
    assert len(introduced) == 1
    print(f"✅ 已出场角色：{len(introduced)} 个")
    
    # 导出认知状态
    state = manager.export_knowledge_state(10)
    assert 'protagonist_name' in state
    assert 'known_knowledge' in state
    assert 'unknown_knowledge' in state
    print("✅ 认知状态导出正常")
    
    print("\n✅ 主角认知管理器测试通过\n")


def test_outline_rewriter():
    """测试大纲转写器"""
    print("="*60)
    print("测试 4: 大纲转写器和后处理器")
    print("="*60)
    
    # 测试移除标签
    text_with_tags = "【场景】主角来到山洞。[重要]这里有宝藏。"
    cleaned = OutlineRewriter.remove_explicit_tags(text_with_tags)
    assert '【' not in cleaned
    assert '[' not in cleaned
    print("✅ 标签移除功能正常")
    
    # 测试列表转换
    list_text = """
    主角面对三个挑战：
    一、击败守门人
    二、破解机关阵
    三、通过心魔考验
    """
    converted = OutlineRewriter.convert_list_to_narrative(list_text)
    assert '一、' not in converted
    assert '二、' not in converted
    print("✅ 列表转换功能正常")
    
    # 测试后处理过滤
    generated_text = """
    【场景】林枫来到山洞。
    
    与此同时，反派正在密谋。
    
    首先，他检查了洞口。其次，他点燃火把。
    """
    
    cleaned, issues = PostProcessor.filter_and_clean(generated_text)
    assert len(issues) > 0
    print(f"✅ 后处理发现 {len(issues)} 个问题")
    
    for issue in issues:
        print(f"  - [{issue['severity']}] {issue['type']}: {issue['description']}")
    
    # 测试改进建议
    suggestions = PostProcessor.suggest_improvements(cleaned, emotion_intensity=8.5)
    print(f"✅ 生成 {len(suggestions)} 条改进建议")
    
    print("\n✅ 大纲转写器和后处理器测试通过\n")


def test_integration():
    """集成测试 - 模拟完整的章节生成流程"""
    print("="*60)
    print("测试 5: 完整集成测试")
    print("="*60)
    
    # 1. 创建节奏控制器，规划情绪曲线
    print("\n步骤 1: 规划情绪曲线")
    controller = PacingController(total_chapters=10, story_structure="three_act")
    curve = controller.plan_emotion_curve()
    print(f"  ✅ 规划了 {len(curve)} 章的情绪曲线")
    
    # 2. 创建认知管理器，设置主角知识和角色
    print("\n步骤 2: 初始化主角认知")
    manager = CharacterKnowledgeManager(protagonist_name="主角")
    
    manager.add_knowledge(
        "world_001",
        "世界观基础设定",
        KnowledgeType.WORLD_SETTING,
        is_initially_known=True,
    )
    
    manager.add_character(
        "ally_001",
        "盟友",
        "ally",
        appearance_priority=1,
    )
    
    print("  ✅ 主角认知和角色库初始化完成")
    
    # 3. 为第1章生成 Prompt
    print("\n步骤 3: 生成第1章 Prompt")
    pacing = controller.get_chapter_pacing(1)
    state = manager.export_knowledge_state(1)
    
    project_info = {
        'title': '集成测试小说',
        'genre': '玄幻',
        'style': '热血',
        'worldview': '修仙世界',
        'chapter_length': 3000,
    }
    
    prompt = generate_chapter_prompt(
        project_info=project_info,
        chapter_number=1,
        outline="主角踏上修仙之路",
        emotion_intensity_target=pacing['emotion_intensity'],
        character_knowledge={
            'known_facts': state['known_knowledge']['world_setting'],
            'unknown_facts': state['unknown_knowledge']['world_setting'],
        },
        active_characters=state['introduced_characters'],
    )
    
    assert '集成测试小说' in prompt
    assert str(pacing['emotion_intensity']) in prompt
    print("  ✅ 第1章 Prompt 生成成功")
    
    # 4. 模拟生成的文本（带有问题）
    print("\n步骤 4: 后处理生成的文本")
    simulated_output = """
    【开篇】主角林枫站在山脚下。
    
    与此同时，远方的反派正在密谋。
    
    首先，林枫深吸一口气。其次，他迈出了第一步。
    """
    
    cleaned, issues = PostProcessor.filter_and_clean(simulated_output)
    print(f"  ✅ 发现并处理了 {len(issues)} 个问题")
    
    # 5. 验证视角一致性
    print("\n步骤 5: 验证视角一致性")
    perspective_issues = PostProcessor.validate_perspective(
        cleaned,
        protagonist_knowledge=state,
    )
    print(f"  ✅ 视角检查完成，发现 {len(perspective_issues)} 个问题")
    
    # 6. 生成改进建议
    print("\n步骤 6: 生成改进建议")
    suggestions = PostProcessor.suggest_improvements(
        cleaned,
        emotion_intensity=pacing['emotion_intensity'],
    )
    print(f"  ✅ 生成了 {len(suggestions)} 条改进建议")
    
    print("\n✅ 完整集成测试通过\n")


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("第四阶段集成测试")
    print("="*60 + "\n")
    
    try:
        test_prompt_templates()
        test_pacing_controller()
        test_character_knowledge_manager()
        test_outline_rewriter()
        test_integration()
        
        print("="*60)
        print("🎉 所有测试通过！")
        print("="*60)
        return 0
        
    except Exception as e:
        print(f"\n❌ 测试失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
