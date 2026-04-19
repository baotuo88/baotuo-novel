# AIMETA P=发布导出服务_多格式导出|R=章节聚合_导出构建|NR=不含HTTP路由|E=ExportService|X=internal|A=服务类|D=zipfile,sqlalchemy|S=db,mem|RD=./README.ai
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Dict, List, Optional, Sequence
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Chapter, ChapterOutline, NovelProject
from .novel_service import NovelService


@dataclass
class ExportChapter:
    chapter_number: int
    title: str
    summary: Optional[str]
    content: str


@dataclass
class ExportResult:
    content: bytes
    filename: str
    media_type: str


class ExportService:
    """项目发布导出服务，支持 markdown/txt/docx/epub。"""

    SUPPORTED_FORMATS = {"markdown", "txt", "docx", "epub"}
    SUPPORTED_TOC_STYLES = {"none", "compact", "detailed"}

    def __init__(self, session: AsyncSession):
        self.session = session
        self.novel_service = NovelService(session)

    async def get_publish_summary(self, project_id: str, user_id: int) -> Dict[str, object]:
        project = await self.novel_service.ensure_project_owner(project_id, user_id)
        chapters = sorted(project.chapters or [], key=lambda item: item.chapter_number)
        outlines = sorted(project.outlines or [], key=lambda item: item.chapter_number)

        generated_numbers = [item.chapter_number for item in chapters if self._resolve_chapter_content(item)]
        chapter_numbers = sorted({item.chapter_number for item in outlines} | {item.chapter_number for item in chapters})

        return {
            "project_id": project_id,
            "title": self._resolve_project_title(project),
            "chapter_total": len(chapter_numbers),
            "outline_total": len(outlines),
            "generated_chapter_total": len(generated_numbers),
            "first_chapter_number": chapter_numbers[0] if chapter_numbers else None,
            "last_chapter_number": chapter_numbers[-1] if chapter_numbers else None,
            "latest_generated_chapter": max(generated_numbers) if generated_numbers else None,
            "generated_at": datetime.utcnow().isoformat(),
        }

    async def export_project(
        self,
        *,
        project_id: str,
        user_id: int,
        export_format: str,
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        include_outline: bool = True,
        include_metadata: bool = True,
        toc_style: str = "compact",
    ) -> ExportResult:
        normalized_format = (export_format or "").strip().lower()
        if normalized_format not in self.SUPPORTED_FORMATS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的导出格式: {export_format}",
            )
        normalized_toc_style = (toc_style or "compact").strip().lower()
        if normalized_toc_style not in self.SUPPORTED_TOC_STYLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的目录样式: {toc_style}",
            )

        if start_chapter and end_chapter and start_chapter > end_chapter:
            raise HTTPException(status_code=400, detail="start_chapter 不能大于 end_chapter")

        project = await self.novel_service.ensure_project_owner(project_id, user_id)
        title = self._resolve_project_title(project)
        chapters = self._collect_export_chapters(
            project=project,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
        )
        if not chapters:
            raise HTTPException(status_code=400, detail="当前范围内没有可导出的章节内容")

        if normalized_format == "markdown":
            content = self._build_markdown(
                title=title,
                chapters=chapters,
                include_outline=include_outline,
                include_metadata=include_metadata,
                toc_style=normalized_toc_style,
            ).encode("utf-8")
            media_type = "text/markdown; charset=utf-8"
            extension = "md"
        elif normalized_format == "txt":
            content = self._build_text(
                title=title,
                chapters=chapters,
                include_outline=include_outline,
                include_metadata=include_metadata,
                toc_style=normalized_toc_style,
            ).encode("utf-8")
            media_type = "text/plain; charset=utf-8"
            extension = "txt"
        elif normalized_format == "docx":
            content = self._build_docx(
                title=title,
                chapters=chapters,
                include_outline=include_outline,
                include_metadata=include_metadata,
                toc_style=normalized_toc_style,
            )
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            extension = "docx"
        else:
            content = self._build_epub(
                title=title,
                chapters=chapters,
                include_outline=include_outline,
                include_metadata=include_metadata,
            )
            media_type = "application/epub+zip"
            extension = "epub"

        scope = (
            f"ch{chapters[0].chapter_number}-{chapters[-1].chapter_number}"
            if chapters
            else "empty"
        )
        safe_title = self._safe_filename(title)
        filename = f"{safe_title}_{scope}.{extension}"
        return ExportResult(content=content, filename=filename, media_type=media_type)

    async def export_project_batch(
        self,
        *,
        project_id: str,
        user_id: int,
        formats: Sequence[str],
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None,
        include_outline: bool = True,
        include_metadata: bool = True,
        toc_style: str = "compact",
    ) -> ExportResult:
        normalized: List[str] = []
        seen = set()
        for item in formats:
            name = str(item or "").strip().lower()
            if not name or name in seen:
                continue
            if name not in self.SUPPORTED_FORMATS:
                raise HTTPException(status_code=400, detail=f"不支持的导出格式: {item}")
            seen.add(name)
            normalized.append(name)
        if not normalized:
            raise HTTPException(status_code=400, detail="至少需要一个导出格式")
        if len(normalized) > 8:
            raise HTTPException(status_code=400, detail="批量导出格式数量不能超过 8")

        entries: List[ExportResult] = []
        for fmt in normalized:
            entries.append(
                await self.export_project(
                    project_id=project_id,
                    user_id=user_id,
                    export_format=fmt,
                    start_chapter=start_chapter,
                    end_chapter=end_chapter,
                    include_outline=include_outline,
                    include_metadata=include_metadata,
                    toc_style=toc_style,
                )
            )

        project = await self.novel_service.ensure_project_owner(project_id, user_id)
        title = self._resolve_project_title(project)
        safe_title = self._safe_filename(title)
        scope = (
            f"ch{start_chapter}-{end_chapter}"
            if (start_chapter is not None and end_chapter is not None)
            else "all"
        )
        batch_name = f"{safe_title}_{scope}_bundle.zip"

        buffer = io.BytesIO()
        manifest = {
            "project_id": project_id,
            "title": title,
            "created_at": datetime.utcnow().isoformat(),
            "formats": normalized,
            "file_count": len(entries),
        }
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for item in entries:
                archive.writestr(item.filename, item.content)

        return ExportResult(
            content=buffer.getvalue(),
            filename=batch_name,
            media_type="application/zip",
        )

    async def send_export_webhook(
        self,
        *,
        webhook_url: str,
        payload: Dict[str, object],
        timeout_seconds: float = 6.0,
    ) -> None:
        url = str(webhook_url or "").strip()
        if not url:
            return
        async with httpx.AsyncClient(timeout=max(1.0, float(timeout_seconds))) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

    @staticmethod
    def build_content_disposition(filename: str) -> str:
        ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "export.bin"
        quoted = quote(filename)
        return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'

    def _collect_export_chapters(
        self,
        *,
        project: NovelProject,
        start_chapter: Optional[int],
        end_chapter: Optional[int],
    ) -> List[ExportChapter]:
        outlines: Dict[int, ChapterOutline] = {
            item.chapter_number: item for item in (project.outlines or [])
        }

        output: List[ExportChapter] = []
        chapter_rows = sorted(project.chapters or [], key=lambda row: row.chapter_number)
        for row in chapter_rows:
            chapter_number = int(row.chapter_number or 0)
            if chapter_number <= 0:
                continue
            if start_chapter is not None and chapter_number < start_chapter:
                continue
            if end_chapter is not None and chapter_number > end_chapter:
                continue

            content = self._resolve_chapter_content(row)
            if not content:
                continue
            outline = outlines.get(chapter_number)
            title = (
                str(outline.title).strip()
                if outline and outline.title
                else f"第{chapter_number}章"
            )
            summary = None
            if outline and outline.summary:
                summary = str(outline.summary).strip() or None
            elif row.real_summary:
                summary = str(row.real_summary).strip() or None
            output.append(
                ExportChapter(
                    chapter_number=chapter_number,
                    title=title,
                    summary=summary,
                    content=content,
                )
            )
        return output

    @staticmethod
    def _resolve_chapter_content(chapter: Chapter) -> str:
        if chapter.selected_version and chapter.selected_version.content:
            return str(chapter.selected_version.content).strip()
        if chapter.versions:
            for version in reversed(chapter.versions):
                if version and version.content:
                    text = str(version.content).strip()
                    if text:
                        return text
        return ""

    @staticmethod
    def _resolve_project_title(project: NovelProject) -> str:
        if project.blueprint and project.blueprint.title:
            title = str(project.blueprint.title).strip()
            if title:
                return title
        title = str(project.title or "").strip()
        return title or "未命名小说"

    @staticmethod
    def _safe_filename(value: str) -> str:
        stripped = str(value or "").strip()
        if not stripped:
            return "novel_export"
        normalized = re.sub(r"[\\/:*?\"<>|]+", "_", stripped)
        normalized = re.sub(r"\s+", "_", normalized)
        return normalized[:80] or "novel_export"

    def _build_markdown(
        self,
        *,
        title: str,
        chapters: Sequence[ExportChapter],
        include_outline: bool,
        include_metadata: bool,
        toc_style: str,
    ) -> str:
        lines: List[str] = [f"# {title}", ""]
        if include_metadata:
            lines.extend(
                [
                    f"- 导出时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    f"- 章节数量：{len(chapters)}",
                    f"- 章节范围：第{chapters[0].chapter_number}章 - 第{chapters[-1].chapter_number}章",
                    "",
                    "---",
                    "",
                ]
            )
        lines.extend(self._build_toc_lines(chapters=chapters, toc_style=toc_style, format_name="markdown"))

        for chapter in chapters:
            lines.append(f"## 第{chapter.chapter_number}章 {chapter.title}")
            lines.append("")
            if include_outline and chapter.summary:
                lines.append("> 章节摘要")
                lines.append(">")
                for line in chapter.summary.splitlines():
                    lines.append(f"> {line}")
                lines.append("")
            lines.append(chapter.content.strip())
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _build_text(
        self,
        *,
        title: str,
        chapters: Sequence[ExportChapter],
        include_outline: bool,
        include_metadata: bool,
        toc_style: str,
    ) -> str:
        lines: List[str] = [title, "=" * max(8, len(title)), ""]
        if include_metadata:
            lines.extend(
                [
                    f"导出时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    f"章节数量：{len(chapters)}",
                    f"章节范围：第{chapters[0].chapter_number}章 - 第{chapters[-1].chapter_number}章",
                    "",
                    "=" * 36,
                    "",
                ]
            )
        lines.extend(self._build_toc_lines(chapters=chapters, toc_style=toc_style, format_name="txt"))

        for chapter in chapters:
            lines.append(f"第{chapter.chapter_number}章 {chapter.title}")
            lines.append("-" * 24)
            if include_outline and chapter.summary:
                lines.append("【章节摘要】")
                lines.append(chapter.summary)
                lines.append("")
            lines.append(chapter.content.strip())
            lines.append("")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    def _build_docx(
        self,
        *,
        title: str,
        chapters: Sequence[ExportChapter],
        include_outline: bool,
        include_metadata: bool,
        toc_style: str,
    ) -> bytes:
        paragraphs: List[str] = [title, ""]
        if include_metadata:
            paragraphs.extend(
                [
                    f"导出时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    f"章节数量：{len(chapters)}",
                    "",
                ]
            )
        paragraphs.extend(self._build_toc_lines(chapters=chapters, toc_style=toc_style, format_name="docx"))
        for chapter in chapters:
            paragraphs.append(f"第{chapter.chapter_number}章 {chapter.title}")
            if include_outline and chapter.summary:
                paragraphs.append("章节摘要：")
                paragraphs.extend(chapter.summary.splitlines() or [""])
            paragraphs.extend(chapter.content.splitlines() or [""])
            paragraphs.append("")

        document_xml = self._build_docx_document_xml(paragraphs)
        content_types_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
"""
        rels_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
"""
        word_rels_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>
"""

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", content_types_xml)
            archive.writestr("_rels/.rels", rels_xml)
            archive.writestr("word/document.xml", document_xml)
            archive.writestr("word/_rels/document.xml.rels", word_rels_xml)
        return buffer.getvalue()

    @staticmethod
    def _build_docx_document_xml(paragraphs: Sequence[str]) -> str:
        body_chunks: List[str] = []
        for text in paragraphs:
            escaped = escape(text or "")
            if not escaped:
                body_chunks.append("<w:p/>")
                continue
            body_chunks.append(
                "<w:p><w:r><w:t xml:space=\"preserve\">"
                + escaped +
                "</w:t></w:r></w:p>"
            )

        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
            "<w:body>"
            + "".join(body_chunks)
            + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\"/></w:sectPr>"
            + "</w:body></w:document>"
        )

    def _build_epub(
        self,
        *,
        title: str,
        chapters: Sequence[ExportChapter],
        include_outline: bool,
        include_metadata: bool,
    ) -> bytes:
        book_id = uuid4().hex
        created_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        chapter_files: List[tuple[str, str, str]] = []
        for index, chapter in enumerate(chapters, start=1):
            file_name = f"chapter-{index:04d}.xhtml"
            chapter_title = f"第{chapter.chapter_number}章 {chapter.title}"
            chapter_files.append(
                (
                    file_name,
                    chapter_title,
                    self._build_epub_chapter_xhtml(
                        chapter_title=chapter_title,
                        summary=chapter.summary if include_outline else None,
                        content=chapter.content,
                    ),
                )
            )

        intro_name = "intro.xhtml"
        intro_xhtml = self._build_epub_intro_xhtml(
            title=title,
            chapter_count=len(chapters),
            include_metadata=include_metadata,
            created_at=created_at,
            first_number=chapters[0].chapter_number if chapters else None,
            last_number=chapters[-1].chapter_number if chapters else None,
        )

        manifest_items = [
            '<item id="nav" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
            '<item id="intro" href="intro.xhtml" media-type="application/xhtml+xml"/>',
        ]
        spine_items = ['<itemref idref="intro"/>']
        toc_links = ['<li><a href="intro.xhtml">导出信息</a></li>']
        for idx, (file_name, chapter_title, _) in enumerate(chapter_files, start=1):
            manifest_items.append(
                f'<item id="chapter{idx}" href="{file_name}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="chapter{idx}"/>')
            toc_links.append(f'<li><a href="{file_name}">{escape(chapter_title)}</a></li>')

        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

        content_opf = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<package xmlns=\"http://www.idpf.org/2007/opf\" unique-identifier=\"bookid\" version=\"3.0\">"
            "<metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
            f"<dc:identifier id=\"bookid\">urn:uuid:{book_id}</dc:identifier>"
            f"<dc:title>{escape(title)}</dc:title>"
            "<dc:language>zh-CN</dc:language>"
            f"<meta property=\"dcterms:modified\">{created_at}</meta>"
            "</metadata>"
            "<manifest>"
            + "".join(manifest_items)
            + "</manifest>"
            "<spine>"
            + "".join(spine_items)
            + "</spine>"
            "</package>"
        )

        toc_xhtml = (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\" xmlns:epub=\"http://www.idpf.org/2007/ops\" lang=\"zh-CN\">"
            "<head><title>目录</title></head><body>"
            f"<nav epub:type=\"toc\" id=\"toc\"><h1>{escape(title)} 目录</h1><ol>"
            + "".join(toc_links)
            + "</ol></nav></body></html>"
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            archive.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr("OEBPS/content.opf", content_opf, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr("OEBPS/toc.xhtml", toc_xhtml, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr(f"OEBPS/{intro_name}", intro_xhtml, compress_type=zipfile.ZIP_DEFLATED)
            for file_name, _, chapter_xhtml in chapter_files:
                archive.writestr(f"OEBPS/{file_name}", chapter_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        return buffer.getvalue()

    @staticmethod
    def _build_toc_lines(
        *,
        chapters: Sequence[ExportChapter],
        toc_style: str,
        format_name: str,
    ) -> List[str]:
        style = (toc_style or "compact").strip().lower()
        if style == "none" or not chapters:
            return []

        if format_name == "markdown":
            lines: List[str] = ["## 目录", ""]
            for chapter in chapters:
                if style == "detailed":
                    summary = (chapter.summary or "").strip().replace("\n", " ")
                    if summary:
                        summary = summary[:48] + ("…" if len(summary) > 48 else "")
                        lines.append(f"- 第{chapter.chapter_number}章 {chapter.title} - {summary}")
                    else:
                        lines.append(f"- 第{chapter.chapter_number}章 {chapter.title}")
                else:
                    lines.append(f"- 第{chapter.chapter_number}章 {chapter.title}")
            lines.extend(["", "---", ""])
            return lines

        lines = ["目录", "-" * 16]
        for chapter in chapters:
            if style == "detailed":
                summary = (chapter.summary or "").strip().replace("\n", " ")
                if summary:
                    summary = summary[:48] + ("…" if len(summary) > 48 else "")
                    lines.append(f"第{chapter.chapter_number}章 {chapter.title} | {summary}")
                else:
                    lines.append(f"第{chapter.chapter_number}章 {chapter.title}")
            else:
                lines.append(f"第{chapter.chapter_number}章 {chapter.title}")
        lines.extend(["", ""])
        return lines

    @staticmethod
    def _build_epub_intro_xhtml(
        *,
        title: str,
        chapter_count: int,
        include_metadata: bool,
        created_at: str,
        first_number: Optional[int],
        last_number: Optional[int],
    ) -> str:
        lines = [f"<h1>{escape(title)}</h1>"]
        if include_metadata:
            lines.append(f"<p>导出时间：{escape(created_at)}</p>")
            lines.append(f"<p>章节数量：{chapter_count}</p>")
            if first_number is not None and last_number is not None:
                lines.append(f"<p>章节范围：第{first_number}章 - 第{last_number}章</p>")
        body = "".join(lines)
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\" lang=\"zh-CN\">"
            "<head><title>导出信息</title></head><body>"
            + body +
            "</body></html>"
        )

    @staticmethod
    def _build_epub_chapter_xhtml(
        *,
        chapter_title: str,
        summary: Optional[str],
        content: str,
    ) -> str:
        lines: List[str] = [f"<h2>{escape(chapter_title)}</h2>"]
        if summary:
            lines.append("<section><h3>章节摘要</h3>")
            for part in summary.splitlines():
                if part.strip():
                    lines.append(f"<p>{escape(part.strip())}</p>")
            lines.append("</section>")
        lines.append("<section>")
        for part in content.splitlines():
            stripped = part.strip()
            if not stripped:
                lines.append("<p>&nbsp;</p>")
            else:
                lines.append(f"<p>{escape(stripped)}</p>")
        lines.append("</section>")
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
            "<html xmlns=\"http://www.w3.org/1999/xhtml\" lang=\"zh-CN\">"
            "<head><title>"
            + escape(chapter_title)
            + "</title></head><body>"
            + "".join(lines)
            + "</body></html>"
        )


__all__ = ["ExportService", "ExportResult"]
