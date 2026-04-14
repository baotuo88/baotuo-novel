# AIMETA P=提示词服务_提示模板管理|R=提示词加载_缓存|NR=不含内容生成|E=PromptService|X=internal|A=服务类|D=sqlalchemy|S=db,fs|RD=./README.ai
import asyncio
import json
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Prompt
from ..repositories.prompt_repository import PromptRepository
from ..repositories.system_config_repository import SystemConfigRepository
from ..schemas.prompt import (
    PromptCreate,
    PromptRead,
    PromptUpdate,
    WritingPresetActivateRequest,
    WritingPresetRead,
    WritingPresetUpsert,
)

_CACHE: Dict[str, PromptRead] = {}
_LOCK = asyncio.Lock()
_LOADED = False
_WRITING_PRESET_CONFIG_KEY = "writer.presets.catalog"
_WRITING_PRESET_ACTIVE_KEY = "writer.preset.active_id"

_BUILTIN_WRITING_PRESETS: list[dict] = [
    {
        "preset_id": "fast-punch",
        "name": "快节奏爽文",
        "description": "冲突密度高、推进快、强调反转和爽点。",
        "prompt_name": "writing_v2",
        "temperature": 0.95,
        "top_p": 0.95,
        "max_tokens": 4200,
        "style_rules": [
            "每 1-2 段推动一次冲突或目标进展，避免拖沓铺垫。",
            "优先使用短句和动作描写，减少抽象叙述。",
            "章节结尾保留悬念或压迫感，形成继续阅读钩子。",
        ],
        "writing_notes_prefix": "本章按快节奏爽文模式执行：冲突先行、节奏紧凑、结尾留钩。",
    },
    {
        "preset_id": "tender-romance",
        "name": "细腻言情",
        "description": "情绪递进细腻，重视人物心理与关系变化。",
        "prompt_name": "writing_v2",
        "temperature": 0.78,
        "top_p": 0.9,
        "max_tokens": 4600,
        "style_rules": [
            "强化微表情、内心独白和感官细节，突出情绪层次。",
            "对话保持含蓄与张力，避免直白说教。",
            "每章至少完成一次关系状态的小幅变化。",
        ],
        "writing_notes_prefix": "本章按细腻言情模式执行：情绪递进优先，关系变化可感知。",
    },
    {
        "preset_id": "suspense-thriller",
        "name": "悬疑惊悚",
        "description": "线索递进、信息克制、持续制造不确定性与压迫感。",
        "prompt_name": "writing_v2",
        "temperature": 0.82,
        "top_p": 0.9,
        "max_tokens": 4600,
        "style_rules": [
            "每章至少推进一条关键线索，同时保留新的疑点。",
            "信息披露采用递进策略，避免一次性解释清楚。",
            "重点场景强化感官细节与心理压迫，结尾保留悬念。",
        ],
        "writing_notes_prefix": "本章按悬疑惊悚模式执行：线索递进、信息克制、结尾留钩。",
    },
]


class PromptService:
    """提示词服务，提供缓存加速与 CRUD 能力。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PromptRepository(session)
        self.system_config_repo = SystemConfigRepository(session)

    async def preload(self) -> None:
        global _CACHE, _LOADED
        prompts = await self.repo.list_all()
        async with _LOCK:
            _CACHE = {item.name: PromptRead.model_validate(item) for item in prompts}
            _LOADED = True

    async def get_prompt(self, name: str) -> Optional[str]:
        global _LOADED
        async with _LOCK:
            if not _LOADED:
                prompts = await self.repo.list_all()
                _CACHE.update({item.name: PromptRead.model_validate(item) for item in prompts})
                _LOADED = True
            cached = _CACHE.get(name)
        if cached:
            return cached.content

        prompt = await self.repo.get_by_name(name)
        if not prompt:
            return None

        prompt_read = PromptRead.model_validate(prompt)
        async with _LOCK:
            _CACHE[name] = prompt_read
        return prompt_read.content

    async def list_prompts(self) -> list[PromptRead]:
        prompts = await self.repo.list_all()
        return [PromptRead.model_validate(item) for item in prompts]

    async def get_prompt_by_id(self, prompt_id: int) -> Optional[PromptRead]:
        instance = await self.repo.get(id=prompt_id)
        if not instance:
            return None
        return PromptRead.model_validate(instance)

    async def create_prompt(self, payload: PromptCreate) -> PromptRead:
        data = payload.model_dump()
        tags = data.get("tags")
        if tags is not None:
            data["tags"] = ",".join(tags)
        prompt = Prompt(**data)
        await self.repo.add(prompt)
        await self.session.commit()
        prompt_read = PromptRead.model_validate(prompt)
        async with _LOCK:
            _CACHE[prompt_read.name] = prompt_read
            global _LOADED
            _LOADED = True
        return prompt_read

    async def update_prompt(self, prompt_id: int, payload: PromptUpdate) -> Optional[PromptRead]:
        instance = await self.repo.get(id=prompt_id)
        if not instance:
            return None
        update_data = payload.model_dump(exclude_unset=True)
        if "tags" in update_data and update_data["tags"] is not None:
            update_data["tags"] = ",".join(update_data["tags"])
        await self.repo.update_fields(instance, **update_data)
        await self.session.commit()
        prompt_read = PromptRead.model_validate(instance)
        async with _LOCK:
            _CACHE[prompt_read.name] = prompt_read
        return prompt_read

    async def delete_prompt(self, prompt_id: int) -> bool:
        instance = await self.repo.get(id=prompt_id)
        if not instance:
            return False
        await self.repo.delete(instance)
        await self.session.commit()
        async with _LOCK:
            _CACHE.pop(instance.name, None)
        return True

    async def _load_custom_writing_presets(self) -> list[dict]:
        record = await self.system_config_repo.get_by_key(_WRITING_PRESET_CONFIG_KEY)
        if not record or not record.value:
            return []
        try:
            parsed = json.loads(record.value)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        sanitized: list[dict] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            try:
                preset = WritingPresetUpsert.model_validate(item)
            except Exception:
                continue
            sanitized.append(preset.model_dump())
        return sanitized

    async def _save_custom_writing_presets(self, presets: list[dict]) -> None:
        value = json.dumps(presets, ensure_ascii=False)
        record = await self.system_config_repo.get_by_key(_WRITING_PRESET_CONFIG_KEY)
        if record:
            record.value = value
            if not record.description:
                record.description = "写作预设目录（JSON）"
        else:
            from ..models import SystemConfig

            self.session.add(
                SystemConfig(
                    key=_WRITING_PRESET_CONFIG_KEY,
                    value=value,
                    description="写作预设目录（JSON）",
                )
            )

    async def _get_active_preset_id(self) -> Optional[str]:
        record = await self.system_config_repo.get_by_key(_WRITING_PRESET_ACTIVE_KEY)
        if not record or not record.value:
            return None
        value = record.value.strip()
        return value or None

    async def _set_active_preset_id(self, preset_id: Optional[str]) -> None:
        record = await self.system_config_repo.get_by_key(_WRITING_PRESET_ACTIVE_KEY)
        value = (preset_id or "").strip()
        if record:
            record.value = value
            if not record.description:
                record.description = "当前启用的写作预设 ID。"
            return
        from ..models import SystemConfig

        self.session.add(
            SystemConfig(
                key=_WRITING_PRESET_ACTIVE_KEY,
                value=value,
                description="当前启用的写作预设 ID。",
            )
        )

    async def list_writing_presets(self) -> list[WritingPresetRead]:
        active_preset_id = await self._get_active_preset_id()
        custom_items = await self._load_custom_writing_presets()
        merged: dict[str, WritingPresetRead] = {}

        for builtin in _BUILTIN_WRITING_PRESETS:
            item = WritingPresetRead.model_validate(
                {
                    **builtin,
                    "is_builtin": True,
                    "is_active": active_preset_id == builtin["preset_id"],
                }
            )
            merged[item.preset_id] = item

        for custom in custom_items:
            item = WritingPresetRead.model_validate(
                {
                    **custom,
                    "is_builtin": False,
                    "is_active": active_preset_id == custom["preset_id"],
                }
            )
            merged[item.preset_id] = item

        result = sorted(
            merged.values(),
            key=lambda item: (
                0 if item.is_active else 1,
                0 if item.is_builtin else 1,
                item.name,
            ),
        )
        return result

    async def upsert_writing_preset(self, payload: WritingPresetUpsert) -> WritingPresetRead:
        if any(item["preset_id"] == payload.preset_id for item in _BUILTIN_WRITING_PRESETS):
            raise ValueError("内置预设不可直接修改，请另存为新的 preset_id")

        custom_items = await self._load_custom_writing_presets()
        payload_data = payload.model_dump()
        updated = False
        for index, item in enumerate(custom_items):
            if item.get("preset_id") == payload.preset_id:
                custom_items[index] = payload_data
                updated = True
                break
        if not updated:
            custom_items.append(payload_data)

        await self._save_custom_writing_presets(custom_items)
        await self.session.commit()

        active_preset_id = await self._get_active_preset_id()
        return WritingPresetRead.model_validate(
            {
                **payload_data,
                "is_builtin": False,
                "is_active": active_preset_id == payload.preset_id,
            }
        )

    async def delete_writing_preset(self, preset_id: str) -> bool:
        if any(item["preset_id"] == preset_id for item in _BUILTIN_WRITING_PRESETS):
            raise ValueError("内置预设不可删除")

        custom_items = await self._load_custom_writing_presets()
        filtered = [item for item in custom_items if item.get("preset_id") != preset_id]
        if len(filtered) == len(custom_items):
            return False

        await self._save_custom_writing_presets(filtered)
        active_preset_id = await self._get_active_preset_id()
        if active_preset_id == preset_id:
            await self._set_active_preset_id(None)
        await self.session.commit()
        return True

    async def activate_writing_preset(self, payload: WritingPresetActivateRequest) -> Optional[WritingPresetRead]:
        preset_id = (payload.preset_id or "").strip() or None
        if preset_id is None:
            await self._set_active_preset_id(None)
            await self.session.commit()
            return None

        presets = await self.list_writing_presets()
        target = next((item for item in presets if item.preset_id == preset_id), None)
        if not target:
            raise ValueError("预设不存在")

        await self._set_active_preset_id(preset_id)
        await self.session.commit()

        return WritingPresetRead.model_validate({**target.model_dump(), "is_active": True})

    async def get_active_writing_preset(self) -> Optional[WritingPresetRead]:
        active_preset_id = await self._get_active_preset_id()
        if not active_preset_id:
            return None
        presets = await self.list_writing_presets()
        return next((item for item in presets if item.preset_id == active_preset_id), None)

    async def get_active_writing_preset_context(self) -> dict:
        preset = await self.get_active_writing_preset()
        if not preset:
            return {}
        style_rules = [rule.strip() for rule in preset.style_rules if rule and rule.strip()]
        return {
            "preset_id": preset.preset_id,
            "preset_name": preset.name,
            "prompt_name": preset.prompt_name.strip() or "writing_v2",
            "temperature": float(preset.temperature),
            "top_p": float(preset.top_p) if preset.top_p is not None else None,
            "max_tokens": int(preset.max_tokens) if preset.max_tokens is not None else None,
            "style_rules": style_rules,
            "style_rules_text": "\n".join(f"- {rule}" for rule in style_rules),
            "writing_notes_prefix": (preset.writing_notes_prefix or "").strip(),
        }
