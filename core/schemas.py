"""Generic domain model. The SHAPE is fixed; the CONTENT (which sections/fields exist) comes from usecase.yaml.
So a new use case needs no Python change: title + summary + fields{} + sections{key: [Item]}."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Item(BaseModel):
    text: str = Field(..., description="One clear sentence")
    owner: str | None = None
    deadline: str | None = None
    evidence: str = Field("", description="Verbatim quote from the input supporting this item")
    confidence: float = Field(0.7, ge=0, le=1)
    attributes: dict[str, str] = Field(default_factory=dict)  # section-specific extras, e.g. severity
    # set by the verifier / reviewer, not by the LLM
    grounded: bool = True
    status: str = "open"

    model_config = {"extra": "allow"}

    @field_validator("owner", "deadline", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str) and v.strip().lower() in {"", "none", "null", "n/a", "unknown", "unassigned"}:
            return None
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v):
        try:
            return min(max(float(v), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.5

    def model_post_init(self, _ctx) -> None:
        # LLMs often put attributes at top level ("severity": "high") -> move them into attributes
        for k, v in list((self.model_extra or {}).items()):
            if isinstance(v, (str, int, float)) and v is not None:
                self.attributes.setdefault(k, str(v))
        if self.model_extra:
            self.model_extra.clear()


class Insights(BaseModel):
    title: str = "Untitled"
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    fields: dict[str, str] = Field(default_factory=dict)
    sections: dict[str, list[Item]] = Field(default_factory=dict)

    @field_validator("fields", mode="before")
    @classmethod
    def _fields_to_str(cls, v):
        return {k: ("" if x is None else str(x)) for k, x in (v or {}).items()}

    def items(self, key: str) -> list[Item]:
        return self.sections.setdefault(key, [])

    def all_items(self):
        for key, items in self.sections.items():
            for it in items:
                yield key, it

    def normalise(self, section_keys: list[str]) -> "Insights":
        """Drop sections the use case doesn't define, add empty ones it does."""
        self.sections = {k: self.sections.get(k, []) for k in section_keys}
        return self
