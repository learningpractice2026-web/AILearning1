"""Loads and validates usecases/<USECASE>/usecase.yaml — the single source of truth for a use case.
A broken YAML fails fast with a readable error instead of a half-working app."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from core.config import ROOT_DIR

USECASES_DIR = ROOT_DIR / "usecases"


class Attribute(BaseModel):
    name: str
    options: list[str] = Field(default_factory=list)   # empty = free text
    description: str = ""


class Section(BaseModel):
    key: str
    label: str
    icon: str = "•"
    description: str = ""
    owner_label: str = "Owner"
    has_owner: bool = True
    has_deadline: bool = False
    is_task: bool = False
    keywords: list[str] = Field(default_factory=list)
    attributes: list[Attribute] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def _snake(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", v):
            raise ValueError(f"section key '{v}' must be snake_case")
        return v

    def keyword_regex(self) -> re.Pattern | None:
        if not self.keywords:
            return None
        parts = [k if k.startswith("\\") or k.endswith("$") else rf"\b{k}\b" for k in self.keywords]
        return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


class Field_(BaseModel):
    name: str
    label: str = ""
    options: list[str] = Field(default_factory=list)
    description: str = ""
    keywords: dict[str, list[str]] = Field(default_factory=dict)  # option -> regexes (offline engine only)


class AppCfg(BaseModel):
    name: str = "AI Assistant"
    tagline: str = ""
    icon: str = "🧠"
    record_name: str = "Record"
    record_name_plural: str = "Records"
    input_label: str = "Input text"
    input_help: str = ""
    accepts_audio: bool = False
    dialogue: bool = False


class AICfg(BaseModel):
    role: str = "a meticulous enterprise analyst"
    task: str = "Extract structured, accurate information from the input."
    rules: list[str] = Field(default_factory=list)


class OfflineCfg(BaseModel):
    priority: list[str] = Field(default_factory=list)
    min_words: int = 4


class GuardrailCfg(BaseModel):
    blocked_terms: list[str] = Field(default_factory=list)   # flag output items containing these
    max_input_chars: int = 200_000                            # reject absurdly large inputs (cost / DoS guard)


class ChatCfg(BaseModel):
    enabled: bool = True
    examples: list[str] = Field(default_factory=list)


class UseCase(BaseModel):
    slug: str = ""
    app: AppCfg = AppCfg()
    ai: AICfg = AICfg()
    fields: list[Field_] = Field(default_factory=list)
    sections: list[Section]
    offline: OfflineCfg = OfflineCfg()
    guardrails: GuardrailCfg = GuardrailCfg()
    chat: ChatCfg = ChatCfg()

    @property
    def dir(self) -> Path:
        return USECASES_DIR / self.slug

    @property
    def samples_dir(self) -> Path:
        return self.dir / "samples"

    @property
    def task_section(self) -> Section:
        return next((s for s in self.sections if s.is_task), self.sections[0])

    def section(self, key: str) -> Section:
        return next(s for s in self.sections if s.key == key)

    def priority(self) -> list[Section]:
        order = [self.section(k) for k in self.offline.priority if any(s.key == k for s in self.sections)]
        return order + [s for s in self.sections if s not in order]

    def schema_hint(self) -> str:
        """JSON shape shown to the LLM, generated from the YAML."""
        flds = ",\n    ".join(f'"{f.name}": "{" | ".join(f.options) if f.options else "string"}"' for f in self.fields)
        secs = []
        for s in self.sections:
            attrs = "".join(f', "{a.name}": "{" | ".join(a.options) if a.options else "string"}"' for a in s.attributes)
            owner = '"string|null"' if s.has_owner else "null"
            dl = '"string|null"' if s.has_deadline else "null"
            secs.append(f'    "{s.key}": [{{"text": "string", "owner": {owner}, "deadline": {dl}, '
                        f'"evidence": "verbatim quote", "confidence": 0.0{attrs}}}]   // {s.description}')
        return ("{\n"
                '  "title": "short title",\n'
                '  "summary": "3-5 sentence executive summary",\n'
                '  "highlights": ["key point", "..."],\n'
                f'  "fields": {{\n    {flds}\n  }},\n'
                '  "sections": {\n' + ",\n".join(secs) + "\n  }\n}")


def load_usecase(slug: str | None = None) -> UseCase:
    slug = slug or os.getenv("USECASE", "meeting_notes")
    path = USECASES_DIR / slug / "usecase.yaml"
    if not path.exists():
        available = ", ".join(p.name for p in USECASES_DIR.iterdir()
                              if (p / "usecase.yaml").exists() and not p.name.startswith("_"))
        raise FileNotFoundError(f"Use case '{slug}' not found at {path}. Available: {available}")
    return _load(slug, path.stat().st_mtime)  # re-read automatically when the YAML is saved


@lru_cache(maxsize=16)
def _load(slug: str, _mtime: float) -> UseCase:
    path = USECASES_DIR / slug / "usecase.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML format error in {path.name}: {e}") from e
    uc = UseCase.model_validate({**data, "slug": slug})
    for s in uc.sections:
        s.keyword_regex()  # validate regexes early
    return uc


def get_usecase() -> UseCase:
    return load_usecase(os.getenv("USECASE", "meeting_notes"))
