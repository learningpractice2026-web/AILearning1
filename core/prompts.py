"""Versioned prompt templates (markdown files, reviewable in Git).
Lookup order: usecases/<USECASE>/prompts/<name>_<ver>.md  ->  prompts/<name>_<ver>.md
Version picked by env PROMPT_<NAME>_VERSION (default v1) for A/B tests."""
from __future__ import annotations

import os

from core.config import PROMPTS_DIR
from core.usecase import get_usecase


def load(name: str) -> tuple[str, str, str]:
    """Returns (system, user_template, version_label)."""
    version = os.getenv(f"PROMPT_{name.upper()}_VERSION", "v1")
    override = get_usecase().dir / "prompts" / f"{name}_{version}.md"
    path = override if override.exists() else PROMPTS_DIR / f"{name}_{version}.md"
    raw = path.read_text(encoding="utf-8")
    system = raw.split("## SYSTEM", 1)[1].split("## USER", 1)[0].strip()
    user = raw.split("## USER", 1)[1].strip()
    label = f"{version}{' (use-case override)' if path == override else ''}"
    return system, user, label


def render(template: str, **kw: str) -> str:
    # str.replace instead of str.format so JSON braces in templates are safe
    for k, v in kw.items():
        template = template.replace("{" + k + "}", v)
    return template
