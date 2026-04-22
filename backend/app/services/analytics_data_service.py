from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.novel import Chapter, ChapterOutline, ChapterVersion, NovelProject


@dataclass(slots=True)
class ProjectChapterSnapshot:
    chapter_id: int
    chapter_number: int
    title: str
    summary: str
    content: str
    status: str


async def get_project_or_404(
    session: AsyncSession,
    project_id: str,
    user_id: int,
    *,
    detail: str = "项目不存在或无权访问",
) -> NovelProject:
    result = await session.execute(
        select(NovelProject).where(
            NovelProject.id == project_id,
            NovelProject.user_id == user_id,
        )
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail=detail)
    return project


async def list_project_chapter_snapshots(
    session: AsyncSession,
    project_id: str,
    *,
    completed_only: bool = False,
) -> list[ProjectChapterSnapshot]:
    chapter_stmt = select(Chapter).where(Chapter.project_id == project_id)
    if completed_only:
        chapter_stmt = chapter_stmt.where(Chapter.status == "completed")
    chapter_stmt = chapter_stmt.order_by(Chapter.chapter_number)

    chapter_result = await session.execute(chapter_stmt)
    chapters = chapter_result.scalars().all()
    if not chapters:
        return []

    outline_result = await session.execute(
        select(ChapterOutline).where(ChapterOutline.project_id == project_id).order_by(ChapterOutline.chapter_number)
    )
    outlines = {outline.chapter_number: outline for outline in outline_result.scalars().all()}

    version_ids = [chapter.selected_version_id for chapter in chapters if chapter.selected_version_id]
    versions_by_id: dict[int, ChapterVersion] = {}
    if version_ids:
        version_result = await session.execute(
            select(ChapterVersion).where(ChapterVersion.id.in_(version_ids))
        )
        versions_by_id = {version.id: version for version in version_result.scalars().all()}

    snapshots: list[ProjectChapterSnapshot] = []
    for chapter in chapters:
        outline = outlines.get(chapter.chapter_number)
        version: Optional[ChapterVersion] = None
        if chapter.selected_version_id:
            version = versions_by_id.get(chapter.selected_version_id)

        snapshots.append(
            ProjectChapterSnapshot(
                chapter_id=chapter.id,
                chapter_number=chapter.chapter_number,
                title=(
                    (version.title if version and getattr(version, "title", None) else None)
                    or (outline.title if outline else None)
                    or f"第{chapter.chapter_number}章"
                ),
                summary=outline.summary if outline else "",
                content=version.content if version and version.content else "",
                status=chapter.status,
            )
        )

    return snapshots
