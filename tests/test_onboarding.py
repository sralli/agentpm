"""Tests for the onboarding guide."""

from __future__ import annotations

import pytest
import pytest_asyncio
import yaml
from mcp.server.fastmcp import FastMCP

from tests.conftest import call

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def stores(tmp_path):
    """Create stores with initialized board for onboarding tests."""
    root = tmp_path / ".agendum"
    root.mkdir()

    from agendum.store.board_store import BoardStore
    from agendum.store.learnings_store import LearningsStore
    from agendum.store.memory_store import MemoryStore
    from agendum.store.project_store import ProjectStore

    class Stores:
        def __init__(self, root):
            self._root = root
            self.board = BoardStore(root)
            self.project = ProjectStore(root)
            self.memory = MemoryStore(root)
            self.learnings = LearningsStore(root)

        @property
        def root(self):
            return self._root

    s = Stores(root)
    s.project.init_board("test-board")
    return s


@pytest.fixture
def guide(stores, tmp_path):
    """Create an OnboardingGuide with a fake git root."""
    from agendum.onboarding import OnboardingGuide

    git_root = tmp_path / "repo"
    git_root.mkdir()
    (git_root / ".git").mkdir()
    return OnboardingGuide(stores, git_root=git_root)


@pytest.fixture
def guide_no_git(stores, tmp_path):
    """Create an OnboardingGuide with no git root (path without .git)."""
    from agendum.onboarding import OnboardingGuide

    no_git_dir = tmp_path / "no_git_here"
    no_git_dir.mkdir()
    # Pass a path that exists but has no .git — OnboardingGuide stores it directly
    return OnboardingGuide(stores, git_root=no_git_dir)


@pytest_asyncio.fixture
async def onboard_server(tmp_path):
    """Fresh FastMCP instance with onboarding support."""
    root = tmp_path / ".agendum"
    root.mkdir()

    from agendum.enrichment.pipeline import ContextEnricher
    from agendum.enrichment.sources import DependencySource, MemorySource, ProjectLearningsSource, ProjectRulesSource
    from agendum.store.board_store import BoardStore
    from agendum.store.learnings_store import LearningsStore
    from agendum.store.memory_store import MemoryStore
    from agendum.store.project_store import ProjectStore

    class Stores:
        def __init__(self, root):
            self._root = root
            self.board = BoardStore(root)
            self.project = ProjectStore(root)
            self.memory = MemoryStore(root)
            self.learnings = LearningsStore(root)

        @property
        def root(self):
            return self._root

    stores = Stores(root)
    stores.project.init_board("test-board")

    enricher = ContextEnricher()
    enricher.register(ProjectRulesSource(root))
    enricher.register(MemorySource(stores.memory))
    enricher.register(DependencySource(stores.board))
    enricher.register(ProjectLearningsSource(stores.learnings))

    mcp = FastMCP("agendum-test-onboard")
    from agendum.tools import register

    register(mcp, stores, enricher)

    return mcp, stores


# ── Step: start ───────────────────────────────────────────────────────────


def test_onboard_start_fresh(guide):
    result = guide.run_step("start")
    assert "Welcome to agendum" in result
    assert "usage_mode" in result
    assert "steps" in result.lower()


def test_onboard_start_already_completed(guide, stores):
    config = stores.project.read_config()
    config.onboarding.completed = True
    stores.project._write_config(config)

    result = guide.run_step("start")
    assert "already completed" in result.lower()
    assert "force" in result.lower()


def test_onboard_start_force(guide, stores):
    config = stores.project.read_config()
    config.onboarding.completed = True
    stores.project._write_config(config)

    result = guide.run_step("start", force=True)
    assert "Welcome to agendum" in result


# ── Step: usage_mode ──────────────────────────────────────────────────────


def test_onboard_usage_mode_always(guide, stores):
    result = guide.run_step("usage_mode", usage_mode="always")
    assert "always" in result.lower()

    config = stores.project.read_config()
    assert config.onboarding.usage_mode == "always"


def test_onboard_usage_mode_guided(guide, stores):
    result = guide.run_step("usage_mode", usage_mode="guided")
    assert "guided" in result.lower()

    config = stores.project.read_config()
    assert config.onboarding.usage_mode == "guided"


def test_onboard_usage_mode_available(guide, stores):
    result = guide.run_step("usage_mode", usage_mode="available")
    assert "available" in result.lower()

    config = stores.project.read_config()
    assert config.onboarding.usage_mode == "available"


def test_onboard_usage_mode_invalid(guide):
    result = guide.run_step("usage_mode", usage_mode="invalid")
    assert "error" in result.lower()
    assert "always, guided, available" in result


def test_onboard_usage_mode_empty(guide):
    result = guide.run_step("usage_mode", usage_mode="")
    assert "error" in result.lower()


# ── Step: project ─────────────────────────────────────────────────────────


def test_onboard_project_creation(guide, stores):
    result = guide.run_step("project", project_name="my-app", project_description="Test app")
    assert "my-app" in result
    assert "created" in result.lower()

    projects = stores.project.list_projects()
    assert "my-app" in projects


def test_onboard_project_skip(guide):
    result = guide.run_step("project", project_name="")
    assert "skipped" in result.lower()


# ── Step: learnings ───────────────────────────────────────────────────────


def test_onboard_learnings_seeding(guide, stores):
    result = guide.run_step("learnings", seed_learnings="Use type hints, Write tests first, Keep functions small")
    assert "3" in result
    assert "learning" in result.lower()

    learnings = stores.learnings.list_learnings()
    assert len(learnings) == 3


def test_onboard_learnings_skip(guide):
    result = guide.run_step("learnings", seed_learnings="")
    assert "skipped" in result.lower()


# ── Step: rules ───────────────────────────────────────────────────────────


def test_onboard_rules_generation_new(guide, stores, tmp_path):
    """Creates CLAUDE.md when none exists."""
    guide.run_step("usage_mode", usage_mode="guided")
    result = guide.run_step("rules", test_command="pytest", lint_command="ruff check .")

    assert "generated" in result.lower() or "CLAUDE.md" in result

    git_root = tmp_path / "repo"
    claude_md = git_root / "CLAUDE.md"
    assert claude_md.exists()

    content = claude_md.read_text()
    assert "agendum usage rules" in content
    assert "pm_status" in content
    assert "pytest" in content

    config = stores.project.read_config()
    assert config.onboarding.rules_generated is True


def test_onboard_rules_generation_append(guide, stores, tmp_path):
    """Appends to existing CLAUDE.md without overwriting."""
    git_root = tmp_path / "repo"
    claude_md = git_root / "CLAUDE.md"
    existing_content = "# My Project\n\nExisting rules here.\n"
    claude_md.write_text(existing_content)

    guide.run_step("usage_mode", usage_mode="always")
    result = guide.run_step("rules")

    assert "appended" in result.lower()

    content = claude_md.read_text()
    assert "Existing rules here." in content  # preserved
    assert "agendum usage rules" in content  # added


def test_onboard_rules_already_present(guide, stores, tmp_path):
    """Skips if agendum rules already present."""
    git_root = tmp_path / "repo"
    claude_md = git_root / "CLAUDE.md"
    claude_md.write_text("# My Project\n\n## agendum usage rules\n\nAlready configured.\n")

    result = guide.run_step("rules")
    assert "already contains" in result.lower()


def test_onboard_rules_no_git_root(stores):
    """Returns snippet when git root not found."""
    from agendum.onboarding import OnboardingGuide

    # Pass git_root explicitly as a sentinel to prevent auto-detection
    guide = OnboardingGuide(stores, git_root=None)
    # Override to None after init (which auto-detects)
    guide._git_root = None
    result = guide.run_step("rules")
    assert "could not detect git root" in result.lower()
    assert "agendum usage rules" in result  # snippet provided


# ── Step: done ────────────────────────────────────────────────────────────


def test_onboard_done_marks_completed(guide, stores):
    result = guide.run_step("done")
    assert "complete" in result.lower()

    config = stores.project.read_config()
    assert config.onboarding.completed is True


def test_onboard_done_next_steps(guide, stores):
    stores.project.create_project("my-project")
    result = guide.run_step("done")
    assert "pm_ingest" in result or "pm_add" in result
    assert "pm_next" in result
    assert "pm_done" in result


# ── Step: invalid ─────────────────────────────────────────────────────────


def test_onboard_invalid_step(guide):
    result = guide.run_step("nonexistent")
    assert "error" in result.lower()
    assert "valid steps" in result.lower()


# ── MCP tool integration ─────────────────────────────────────────────────


@pytest.mark.anyio
async def test_pm_onboard_tool_start(onboard_server):
    mcp, stores = onboard_server
    result = await call(mcp, "pm_onboard", step="start")
    assert "Welcome to agendum" in result


@pytest.mark.anyio
async def test_pm_onboard_tool_full_flow(onboard_server):
    mcp, stores = onboard_server

    result = await call(mcp, "pm_onboard", step="start")
    assert "Welcome" in result

    result = await call(mcp, "pm_onboard", step="usage_mode", usage_mode="always")
    assert "always" in result.lower()

    result = await call(mcp, "pm_onboard", step="project", project_name="test-proj", project_description="A test")
    assert "test-proj" in result

    result = await call(mcp, "pm_onboard", step="learnings", seed_learnings="Always test first")
    assert "1" in result

    result = await call(mcp, "pm_onboard", step="done")
    assert "complete" in result.lower()

    config = stores.project.read_config()
    assert config.onboarding.completed is True
    assert config.onboarding.usage_mode == "always"


# ── pm_status onboarding hint ────────────────────────────────────────────


@pytest.mark.anyio
async def test_pm_status_hints_onboarding(onboard_server):
    mcp, stores = onboard_server
    result = await call(mcp, "pm_status")
    assert "pm_onboard" in result


@pytest.mark.anyio
async def test_pm_status_no_hint_after_onboarding(onboard_server):
    mcp, stores = onboard_server

    config = stores.project.read_config()
    config.onboarding.completed = True
    stores.project._write_config(config)

    result = await call(mcp, "pm_status")
    assert "pm_onboard" not in result


# ── Config backward compatibility ─────────────────────────────────────────


def test_config_backward_compatible(tmp_path):
    """Existing config.yaml without onboarding key parses correctly."""
    root = tmp_path / ".agendum"
    root.mkdir()
    config_data = {"version": "1", "name": "old-board", "projects": ["proj1"], "default_project": "proj1"}
    (root / "config.yaml").write_text(yaml.dump(config_data))

    from agendum.store.project_store import ProjectStore

    store = ProjectStore(root)
    config = store.read_config()
    assert config.onboarding.usage_mode == "guided"
    assert config.onboarding.completed is False
