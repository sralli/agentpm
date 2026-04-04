"""agendum MCP server — Project Memory + Scoping Engine."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from agendum.config import resolve_root
from agendum.enrichment.pipeline import ContextEnricher
from agendum.enrichment.sources import DependencySource, MemorySource, ProjectLearningsSource, ProjectRulesSource
from agendum.store.board_store import BoardStore
from agendum.store.learnings_store import LearningsStore
from agendum.store.memory_store import MemoryStore
from agendum.store.project_store import ProjectStore
from agendum.tools import register


class _Stores:
    """Lazy-initialized stores — resolve root at first access."""

    def __init__(self) -> None:
        self._root: Path | None = None
        self._board: BoardStore | None = None
        self._project: ProjectStore | None = None
        self._memory: MemoryStore | None = None
        self._learnings: LearningsStore | None = None
        self._initialized = False

    @property
    def root(self) -> Path:
        if self._root is None:
            self._root = resolve_root()
        return self._root

    def _ensure_initialized(self) -> None:
        """Auto-initialize .agendum/ if it doesn't exist."""
        if self._initialized:
            return
        self._initialized = True  # Set first to prevent recursion
        config_path = self.root / "config.yaml"
        if not config_path.exists():
            from agendum.config import derive_board_name

            self.project.init_board(derive_board_name())

    @property
    def board(self) -> BoardStore:
        self._ensure_initialized()
        if self._board is None:
            self._board = BoardStore(self.root)
        return self._board

    @property
    def project(self) -> ProjectStore:
        if self._project is None:
            self._project = ProjectStore(self.root)
        self._ensure_initialized()
        return self._project

    @property
    def memory(self) -> MemoryStore:
        self._ensure_initialized()
        if self._memory is None:
            self._memory = MemoryStore(self.root)
        return self._memory

    @property
    def learnings(self) -> LearningsStore:
        self._ensure_initialized()
        if self._learnings is None:
            self._learnings = LearningsStore(self.root)
        return self._learnings


stores = _Stores()


class _LazyEnricher:
    """Defers enrichment source registration until first use."""

    def __init__(self) -> None:
        self._inner: ContextEnricher | None = None

    def _init(self) -> ContextEnricher:
        if self._inner is None:
            self._inner = ContextEnricher()
            self._inner.register(ProjectRulesSource(stores.root))
            self._inner.register(MemorySource(stores.memory))
            self._inner.register(DependencySource(stores.board))
            self._inner.register(ProjectLearningsSource(stores.learnings))
        return self._inner

    def enrich(self, *args, **kwargs):
        return self._init().enrich(*args, **kwargs)


enricher = _LazyEnricher()

INSTRUCTIONS = """agendum is a project memory and scoping engine for AI coding agents.

Workflow:
1. pm_onboard() — First-time setup: configure usage rules, create project, generate agent rules
2. pm_project("create", name, description) — Create a project
3. pm_ingest(project, plan_file) — Import tasks from a plan file
4. pm_next(project) — Get a bounded, context-rich work package
5. Implement the task within the specified scope and constraints
6. pm_done(project, item_id) — Record completion with decisions and patterns
7. Repeat steps 4-6. Use pm_status for session resume. Use pm_learn for cross-project insights.

Board initialization is automatic — no setup needed. Just create a project and start working.
First time? Call pm_onboard() for guided setup."""

mcp = FastMCP("agendum", instructions=INSTRUCTIONS)
register(mcp, stores, enricher)
