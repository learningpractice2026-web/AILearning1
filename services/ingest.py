"""Multimodal ingestion — turn any upload into plain text:
   text (txt/md) · captions (vtt/srt) · Word (docx) · PDF (digital text, or scanned → vision model)
   · images (png/jpg/webp → vision model OCR + visual notes) · audio (Whisper)."""
from __future__ import annotations

import io
import re
import tempfile
from pathlib import Path

from core.llm import get_llm

TEXT_EXT = {".txt", ".md"}
CAPTION_EXT = {".vtt", ".srt"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".mp4"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED = sorted(TEXT_EXT | CAPTION_EXT | AUDIO_EXT | IMAGE_EXT | {".docx", ".pdf"})
MAX_BYTES = 25 * 1024 * 1024
MAX_SCANNED_PAGES = 6            # cost guard for vision calls
MIN_TEXT_CHARS_PER_PAGE = 40     # below this a PDF page is treated as scanned


def read_upload(name: str, data: bytes) -> str:
    text, _ = read_upload_with_meta(name, data)
    return text


def read_upload_with_meta(name: str, data: bytes) -> tuple[str, dict]:
    """Returns (text, meta) where meta says which modality/path was used (shown in the UI and logs)."""
    ext = Path(name).suffix.lower()
    if len(data) > MAX_BYTES:
        raise ValueError("File larger than 25 MB. Split it or upload a smaller file.")
    if ext in TEXT_EXT:
        return data.decode("utf-8", errors="replace"), {"modality": "text"}
    if ext in CAPTION_EXT:
        return _captions_to_text(data.decode("utf-8", errors="replace")), {"modality": "captions"}
    if ext == ".docx":
        return _docx(data), {"modality": "docx"}
    if ext == ".pdf":
        return _pdf(data)
    if ext in IMAGE_EXT:
        mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else f"image/{ext.lstrip('.')}"
        return get_llm().vision_to_text([(data, mime)]), {"modality": "image (vision model)"}
    if ext in AUDIO_EXT:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(data)
            tmp = f.name
        try:
            return get_llm().transcribe(tmp), {"modality": "audio (speech-to-text)"}
        finally:
            Path(tmp).unlink(missing_ok=True)
    raise ValueError(f"Unsupported file type {ext}. Supported: {', '.join(SUPPORTED)}")


def _docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:  # tables are often where the facts are
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts)


def _pdf(data: bytes) -> tuple[str, dict]:
    """Digital PDF -> pypdf text. Pages with (almost) no text are scanned -> rendered and read by the vision model."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    scanned = [i for i, t in enumerate(pages) if len(t) < MIN_TEXT_CHARS_PER_PAGE]
    meta = {"modality": "pdf", "pages": len(pages), "scanned_pages": len(scanned)}
    if scanned:
        try:
            images = _render_pages(data, scanned[:MAX_SCANNED_PAGES])
            ocr = get_llm().vision_to_text(images)
            # put OCR text in place of the first scanned page, keep digital text of the others
            for i in scanned[:MAX_SCANNED_PAGES]:
                pages[i] = ""
            pages[scanned[0]] = ocr
            meta["modality"] = "pdf + vision OCR"
            if len(scanned) > MAX_SCANNED_PAGES:
                meta["warning"] = f"Only the first {MAX_SCANNED_PAGES} scanned pages were read (cost guard)."
        except RuntimeError as e:  # no vision model configured
            if not any(pages):
                raise RuntimeError(f"This PDF is scanned (no text layer). {e}") from e
            meta["warning"] = f"{len(scanned)} scanned page(s) skipped: {e}"
    return "\n\n".join(p for p in pages if p), meta


def _render_pages(data: bytes, indexes: list[int]) -> list[tuple[bytes, str]]:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(data)
    out = []
    for i in indexes:
        img = pdf[i].render(scale=1.6).to_pil()
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        out.append((buf.getvalue(), "image/jpeg"))
    return out


def _captions_to_text(raw: str) -> str:
    """Teams/Zoom .vtt exports: drop cue numbers + timestamps, keep '<v Name>' speakers."""
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or line.isdigit() or "-->" in line:
            continue
        m = re.match(r"<v ([^>]+)>(.*?)(</v>)?$", line)
        out.append(f"{m.group(1)}: {m.group(2)}" if m else line)
    return "\n".join(out)
