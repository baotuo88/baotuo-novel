# AIMETA P=数据库初始化_创建表和默认数据|R=创建表_初始化管理员|NR=不含业务逻辑|E=init_db|X=internal|A=初始化函数|D=sqlalchemy|S=db|RD=./README.ai
import logging

from pathlib import Path

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from ..core.config import settings
from ..core.security import hash_password
from ..models import Prompt, SystemConfig, User
from .base import Base
from .system_config_defaults import SYSTEM_CONFIG_DEFAULTS
from .session import AsyncSessionLocal, engine

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """初始化数据库结构并确保默认管理员存在。"""

    await _ensure_database_exists()

    # ---- 第一步：创建所有表结构 ----
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("数据库表结构已初始化")
    await _ensure_schema_updates()

    # ---- 第二步：确保管理员账号至少存在一个 ----
    async with AsyncSessionLocal() as session:
        admin_exists = await session.execute(select(User).where(User.is_admin.is_(True)))
        if not admin_exists.scalars().first():
            if not settings.admin_default_password:
                raise RuntimeError(
                    "未检测到管理员账号，且未配置 ADMIN_DEFAULT_PASSWORD，无法安全初始化默认管理员"
                )
            logger.warning("未检测到管理员账号，正在创建默认管理员 ...")
            admin_user = User(
                username=settings.admin_default_username,
                email=settings.admin_default_email,
                hashed_password=hash_password(settings.admin_default_password),
                is_admin=True,
            )

            session.add(admin_user)
            try:
                await session.commit()
                logger.info("默认管理员创建完成：%s", settings.admin_default_username)
            except IntegrityError:
                await session.rollback()
                logger.exception("默认管理员创建失败，可能是并发启动导致，请检查数据库状态")

        # ---- 第三步：同步系统配置到数据库 ----
        for entry in SYSTEM_CONFIG_DEFAULTS:
            value = entry.value_getter(settings)
            if value is None:
                continue
            existing = await session.get(SystemConfig, entry.key)
            if existing:
                if entry.description and existing.description != entry.description:
                    existing.description = entry.description
                continue
            session.add(
                SystemConfig(
                    key=entry.key,
                    value=value,
                    description=entry.description,
                )
            )

        await _ensure_default_prompts(session)

        await session.commit()


async def _ensure_database_exists() -> None:
    """在首次连接前确认数据库存在，针对不同驱动做最小化准备工作。"""
    url = make_url(settings.sqlalchemy_database_uri)

    if url.get_backend_name() == "sqlite":
        # SQLite 采用文件数据库，确保父目录存在即可，无需额外建库语句
        db_path = Path(url.database or "").expanduser()
        if not db_path.is_absolute():
            project_root = Path(__file__).resolve().parents[2]
            db_path = (project_root / db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return

    database = (url.database or "").strip("/")
    if not database:
        return

    admin_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=None,
        query=url.query,
    )

    admin_engine = create_async_engine(
        admin_url.render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    async with admin_engine.begin() as conn:
        await conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{database}`"))
    await admin_engine.dispose()


async def _ensure_schema_updates() -> None:
    """补齐历史版本缺失的列，避免旧库在新版本报错。"""
    async with engine.begin() as conn:
        def _upgrade(sync_conn):
            def _table_names() -> set[str]:
                return set(inspect(sync_conn).get_table_names())

            def _columns(table_name: str) -> set[str]:
                return {col["name"] for col in inspect(sync_conn).get_columns(table_name)}

            def _indexes(table_name: str) -> set[str]:
                return {idx.get("name") for idx in inspect(sync_conn).get_indexes(table_name) if idx.get("name")}

            def _uniques(table_name: str) -> set[str]:
                inspector = inspect(sync_conn)
                names = {
                    uq.get("name")
                    for uq in inspector.get_unique_constraints(table_name)
                    if uq.get("name")
                }
                for idx in inspector.get_indexes(table_name):
                    if idx.get("unique") and idx.get("name"):
                        names.add(idx["name"])
                return names

            def _create_index_if_missing(
                table_name: str,
                index_name: str,
                columns_sql: str,
                *,
                unique: bool = False,
            ) -> None:
                existing = _uniques(table_name) if unique else _indexes(table_name)
                if index_name in existing:
                    return
                keyword = "UNIQUE INDEX" if unique else "INDEX"
                sync_conn.execute(
                    text(f"CREATE {keyword} {index_name} ON {table_name}({columns_sql})")
                )

            def _dedupe_table_by_keys(table_name: str, key_columns: list[str]) -> None:
                keys = ", ".join(key_columns)
                sync_conn.execute(
                    text(
                        f"""
                        DELETE FROM {table_name}
                        WHERE id NOT IN (
                            SELECT keep_id FROM (
                                SELECT MIN(id) AS keep_id
                                FROM {table_name}
                                GROUP BY {keys}
                            ) dedupe_rows
                        )
                        """
                    )
                )

            table_names = _table_names()

            if "chapter_outlines" in table_names:
                columns = _columns("chapter_outlines")
                if "metadata" not in columns:
                    sync_conn.execute(text("ALTER TABLE chapter_outlines ADD COLUMN metadata JSON"))
                _dedupe_table_by_keys("chapter_outlines", ["project_id", "chapter_number"])
                _create_index_if_missing(
                    "chapter_outlines",
                    "uq_chapter_outlines_project_chapter",
                    "project_id, chapter_number",
                    unique=True,
                )
                _create_index_if_missing(
                    "chapter_outlines",
                    "ix_chapter_outlines_project_chapter",
                    "project_id, chapter_number",
                )

            if "chapters" in table_names:
                _dedupe_table_by_keys("chapters", ["project_id", "chapter_number"])
                _create_index_if_missing(
                    "chapters",
                    "uq_chapters_project_chapter",
                    "project_id, chapter_number",
                    unique=True,
                )
                _create_index_if_missing(
                    "chapters",
                    "ix_chapters_project_chapter",
                    "project_id, chapter_number",
                )

            if "llm_call_logs" in table_names:
                llm_columns = _columns("llm_call_logs")
                if "project_id" not in llm_columns:
                    sync_conn.execute(text("ALTER TABLE llm_call_logs ADD COLUMN project_id VARCHAR(64)"))
                llm_indexes = _indexes("llm_call_logs")
                if "idx_llm_call_logs_project_id" not in llm_indexes and "ix_llm_call_logs_project_id" not in llm_indexes:
                    sync_conn.execute(text("CREATE INDEX idx_llm_call_logs_project_id ON llm_call_logs(project_id)"))

            if "generation_tasks" in table_names:
                task_columns = _columns("generation_tasks")
                if "heartbeat_at" not in task_columns:
                    sync_conn.execute(text("ALTER TABLE generation_tasks ADD COLUMN heartbeat_at DATETIME NULL"))
                    sync_conn.execute(text("CREATE INDEX ix_generation_tasks_heartbeat_at ON generation_tasks(heartbeat_at)"))

            if "factions" in table_names:
                _dedupe_table_by_keys("factions", ["project_id", "name"])
                _create_index_if_missing(
                    "factions",
                    "uq_factions_project_name",
                    "project_id, name",
                    unique=True,
                )
                _create_index_if_missing(
                    "factions",
                    "ix_factions_project_name",
                    "project_id, name",
                )

            if "faction_relationships" in table_names:
                _dedupe_table_by_keys(
                    "faction_relationships",
                    ["project_id", "faction_from_id", "faction_to_id"],
                )
                _create_index_if_missing(
                    "faction_relationships",
                    "uq_faction_relationships_project_pair",
                    "project_id, faction_from_id, faction_to_id",
                    unique=True,
                )
                _create_index_if_missing(
                    "faction_relationships",
                    "ix_faction_relationships_project",
                    "project_id",
                )
                _create_index_if_missing(
                    "faction_relationships",
                    "ix_faction_relationships_from_to",
                    "faction_from_id, faction_to_id",
                )

            if "faction_members" in table_names:
                _dedupe_table_by_keys("faction_members", ["faction_id", "character_id"])
                _create_index_if_missing(
                    "faction_members",
                    "uq_faction_members_faction_character",
                    "faction_id, character_id",
                    unique=True,
                )
                _create_index_if_missing(
                    "faction_members",
                    "ix_faction_members_project",
                    "project_id",
                )
        await conn.run_sync(_upgrade)


async def _ensure_default_prompts(session: AsyncSession) -> None:
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    if not prompts_dir.is_dir():
        return

    result = await session.execute(select(Prompt.name))
    existing_names = set(result.scalars().all())

    for prompt_file in sorted(prompts_dir.glob("*.md")):
        name = prompt_file.stem
        if name in existing_names:
            continue
        content = prompt_file.read_text(encoding="utf-8")
        session.add(Prompt(name=name, content=content))
