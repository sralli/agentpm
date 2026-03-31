"""Heuristic complexity scorer for task-based model routing.

Scores task metadata to auto-assign a TaskCategory when not explicitly provided.
Inspired by OpenClaw Router's multi-dimension approach, adapted for task metadata
rather than prompts.  No LLM calls — pure static heuristics.
"""

from __future__ import annotations

import re

from agendum.models import TaskCategory

# --- Keyword sets (matched case-insensitively as substrings) ---

ARCH_KEYWORDS: frozenset[str] = frozenset(
    {
        "refactor",
        "migrate",
        "redesign",
        "architect",
        "rewrite",
        "infrastructure",
        "schema",
        "migration",
        "framework",
        "abstraction",
        "security",
        "authentication",
        "authorization",
        "encryption",
        "concurrency",
        "distributed",
        "scalab",
        "performance",
        "database",
        "api design",
        "breaking change",
        "backwards compat",
    }
)

SIMPLE_KEYWORDS: frozenset[str] = frozenset(
    {
        "typo",
        "rename",
        "bump",
        "update version",
        "fix lint",
        "add comment",
        "readme",
        "changelog",
        "formatting",
        "whitespace",
        "nit",
        "trivial",
    }
)

# Pre-compile a single regex for each set (word-boundary-free substring match).
_ARCH_PATTERN = re.compile("|".join(re.escape(k) for k in ARCH_KEYWORDS), re.IGNORECASE)
_SIMPLE_PATTERN = re.compile("|".join(re.escape(k) for k in SIMPLE_KEYWORDS), re.IGNORECASE)

# Type → category for non-dev/ops types (direct mapping, no scoring needed).
_DIRECT_CATEGORY: dict[str, TaskCategory] = {
    "docs": TaskCategory.DOCS,
    "email": TaskCategory.EMAIL,
    "planning": TaskCategory.PLANNING,
    "research": TaskCategory.RESEARCH,
    "review": TaskCategory.REVIEW,
    "personal": TaskCategory.PERSONAL,
}

# Priority → numeric value for scoring.
_PRIORITY_SCORE: dict[str, float] = {
    "low": 0.0,
    "medium": 0.3,
    "high": 0.6,
    "critical": 1.0,
}


def _count_score(count: int, thresholds: list[tuple[int, float]]) -> float:
    """Return score based on count crossing thresholds (ascending).

    *thresholds* is a list of ``(min_count, score)`` pairs, checked in reverse
    order so the first (highest) match wins.
    """
    for min_count, score in reversed(thresholds):
        if count >= min_count:
            return score
    return 0.0


def score_complexity(
    title: str,
    description: str = "",
    task_type: str = "dev",
    priority: str = "medium",
    key_files: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    depends_on: list[str] | None = None,
    constraints: list[str] | None = None,
) -> TaskCategory:
    """Score task complexity and return a :class:`TaskCategory`.

    For non-dev/ops task types the category maps directly (docs → DOCS, etc.).
    For ``dev`` and ``ops`` tasks a weighted heuristic score (0–1) determines:

    * < 0.25 → CODE_SIMPLE
    * 0.25–0.55 → CODE_FRONTEND
    * > 0.55 → CODE_COMPLEX
    """
    task_type = task_type.lower()

    # Direct mapping for non-code types.
    if task_type in _DIRECT_CATEGORY:
        return _DIRECT_CATEGORY[task_type]

    # --- Weighted scoring for dev / ops ---
    text = f"{title} {description}".lower()

    # 1. Simple keyword check — early exit.
    if _SIMPLE_PATTERN.search(text):
        return TaskCategory.CODE_SIMPLE

    files = key_files or []
    criteria = acceptance_criteria or []
    deps = depends_on or []
    cons = constraints or []

    # 2. Architectural keywords (weight 0.20).
    arch_score = 1.0 if _ARCH_PATTERN.search(text) else 0.0

    # 3. Key files count (weight 0.20).
    files_score = _count_score(len(files), [(1, 0.2), (3, 0.5), (6, 1.0)])

    # 4. Acceptance criteria count (weight 0.15).
    criteria_score = _count_score(len(criteria), [(2, 0.3), (4, 0.6), (6, 1.0)])

    # 5. Dependency count (weight 0.10).
    deps_score = _count_score(len(deps), [(1, 0.2), (2, 0.5), (4, 1.0)])

    # 6. Priority (weight 0.10).
    priority_score = _PRIORITY_SCORE.get(priority.lower(), 0.3)

    # 7. Constraints count (weight 0.10).
    constraints_score = _count_score(len(cons), [(1, 0.3), (3, 0.7)])

    # Weights sum to 1.0 (simple-keyword case is handled by early exit above).
    weighted = (
        0.25 * arch_score
        + 0.25 * files_score
        + 0.15 * criteria_score
        + 0.10 * deps_score
        + 0.10 * priority_score
        + 0.15 * constraints_score
    )

    if weighted >= 0.40:
        return TaskCategory.CODE_COMPLEX
    if weighted >= 0.20:
        return TaskCategory.CODE_FRONTEND
    return TaskCategory.CODE_SIMPLE
