"""Tests for context enrichment pipeline — Protocol, ContextEnricher, sources, budget."""

from __future__ import annotations

from datetime import UTC, datetime

from agendum.models import (
    AgentHandoffRecord,
    ContextPacket,
    ExternalReference,
    ProgressEntry,
    Task,
    TaskStatus,
)
from agendum.store.memory_store import MemoryStore
from agendum.store.project_store import ProjectStore
from agendum.store.task_store import TaskStore
from agendum.tools.orchestrator.enrichment import ContextEnricher, ContextSource
from agendum.tools.orchestrator.sources import (
    ExternalReferencesSource,
    HandoffSource,
    MemorySource,
    ProjectRulesSource,
    ReviewHistorySource,
)


def _packet(task_id: str = "task-001", goal: str = "Test goal") -> ContextPacket:
    return ContextPacket(task_id=task_id, goal=goal)


def _task(task_id: str = "task-001", title: str = "Test task") -> Task:
    return Task(id=task_id, project="test", title=title, status=TaskStatus.PENDING)


class _StubSource:
    """A simple ContextSource for testing."""

    def __init__(self, name: str, field: str, value: str):
        self.name = name
        self._field = field
        self._value = value

    def enrich(self, packet: ContextPacket, task: Task, project: str) -> ContextPacket:
        return packet.model_copy(update={self._field: self._value})


class TestContextSourceProtocol:
    def test_stub_satisfies_protocol(self):
        source = _StubSource("test", "project_rules", "content")
        assert isinstance(source, ContextSource)

    def test_protocol_requires_name(self):
        class BadSource:
            def enrich(self, packet, task, project):
                return packet

        assert not isinstance(BadSource(), ContextSource)

    def test_protocol_requires_enrich(self):
        class BadSource:
            name = "bad"

        assert not isinstance(BadSource(), ContextSource)


class TestContextEnricher:
    def test_empty_enricher(self):
        enricher = ContextEnricher()
        packet = _packet()
        result = enricher.enrich(packet, _task(), "test")
        assert result.project_rules == ""
        assert result.memory_context == ""

    def test_single_source(self):
        enricher = ContextEnricher()
        enricher.register(_StubSource("rules", "project_rules", "# My Rules"))
        result = enricher.enrich(_packet(), _task(), "test")
        assert result.project_rules == "# My Rules"

    def test_multiple_sources(self):
        enricher = ContextEnricher()
        enricher.register(_StubSource("rules", "project_rules", "rules"))
        enricher.register(_StubSource("memory", "memory_context", "memory"))
        result = enricher.enrich(_packet(), _task(), "test")
        assert result.project_rules == "rules"
        assert result.memory_context == "memory"

    def test_source_chaining_immutable(self):
        """Each source gets the packet enriched by previous sources."""
        enricher = ContextEnricher()
        enricher.register(_StubSource("a", "project_rules", "A"))
        enricher.register(_StubSource("b", "memory_context", "B"))

        original = _packet()
        result = enricher.enrich(original, _task(), "test")

        # Original unchanged
        assert original.project_rules == ""
        assert original.memory_context == ""
        # Result has both
        assert result.project_rules == "A"
        assert result.memory_context == "B"

    def test_disabled_sources_skipped(self):
        enricher = ContextEnricher()
        enricher.register(_StubSource("rules", "project_rules", "rules"))
        enricher.register(_StubSource("memory", "memory_context", "memory"))

        result = enricher.enrich(_packet(), _task(), "test", disabled_sources=["memory"])
        assert result.project_rules == "rules"
        assert result.memory_context == ""

    def test_unregister(self):
        enricher = ContextEnricher()
        enricher.register(_StubSource("rules", "project_rules", "rules"))
        enricher.register(_StubSource("memory", "memory_context", "memory"))

        enricher.unregister("rules")
        assert enricher.source_names == ["memory"]

    def test_source_names(self):
        enricher = ContextEnricher()
        enricher.register(_StubSource("a", "project_rules", ""))
        enricher.register(_StubSource("b", "memory_context", ""))
        assert enricher.source_names == ["a", "b"]


class TestBudgetTruncation:
    def test_no_truncation_when_under_budget(self):
        enricher = ContextEnricher()
        enricher.register(_StubSource("rules", "project_rules", "short"))
        result = enricher.enrich(_packet(), _task(), "test", max_context_chars=8000)
        assert result.project_rules == "short"
        assert "truncated" not in result.project_rules

    def test_truncation_when_over_field_budget(self):
        enricher = ContextEnricher()
        long_content = "x" * 5000
        enricher.register(_StubSource("rules", "project_rules", long_content))
        result = enricher.enrich(_packet(), _task(), "test", max_context_chars=8000)
        # project_rules budget is 3000
        assert len(result.project_rules) < 5000
        assert "truncated" in result.project_rules

    def test_truncation_when_over_total_budget(self):
        enricher = ContextEnricher()
        enricher.register(_StubSource("rules", "project_rules", "x" * 2500))
        enricher.register(_StubSource("deps", "dependency_outputs", "y" * 2500))
        enricher.register(_StubSource("mem", "memory_context", "z" * 2500))
        enricher.register(_StubSource("rev", "review_history", "w" * 2500))

        result = enricher.enrich(_packet(), _task(), "test", max_context_chars=5000)
        total = (
            len(result.project_rules)
            + len(result.dependency_outputs)
            + len(result.memory_context)
            + len(result.review_history)
        )
        assert total <= 5500  # allow some slack for truncation suffix

    def test_empty_fields_not_truncated(self):
        enricher = ContextEnricher()
        result = enricher.enrich(_packet(), _task(), "test", max_context_chars=100)
        assert result.project_rules == ""
        assert result.memory_context == ""


# --- Source Tests ---


class TestProjectRulesSource:
    def test_loads_claude_md(self, tmp_path):
        # Create a fake git repo with CLAUDE.md
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project Rules\nUse ruff. Line length 120.")
        agendum_root = tmp_path / ".agendum"
        agendum_root.mkdir()

        source = ProjectRulesSource(agendum_root)
        result = source.enrich(_packet(), _task(), "test")
        assert "Project Rules" in result.project_rules
        assert any("CLAUDE.md" in p for p in result.pointers)

    def test_prefers_claude_md_over_agents_md(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("CLAUDE content")
        (tmp_path / "AGENTS.md").write_text("AGENTS content")
        agendum_root = tmp_path / ".agendum"
        agendum_root.mkdir()

        source = ProjectRulesSource(agendum_root)
        result = source.enrich(_packet(), _task(), "test")
        assert "CLAUDE content" in result.project_rules

    def test_falls_back_to_agents_md(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "AGENTS.md").write_text("AGENTS content")
        agendum_root = tmp_path / ".agendum"
        agendum_root.mkdir()

        source = ProjectRulesSource(agendum_root)
        result = source.enrich(_packet(), _task(), "test")
        assert "AGENTS content" in result.project_rules

    def test_no_git_root(self, tmp_path):
        # No .git directory — should return packet unchanged
        agendum_root = tmp_path / ".agendum"
        agendum_root.mkdir()

        source = ProjectRulesSource(agendum_root)
        result = source.enrich(_packet(), _task(), "test")
        assert result.project_rules == ""

    def test_no_rule_files(self, tmp_path):
        (tmp_path / ".git").mkdir()
        agendum_root = tmp_path / ".agendum"
        agendum_root.mkdir()

        source = ProjectRulesSource(agendum_root)
        result = source.enrich(_packet(), _task(), "test")
        assert result.project_rules == ""

    def test_truncation(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("x" * 5000)
        agendum_root = tmp_path / ".agendum"
        agendum_root.mkdir()

        source = ProjectRulesSource(agendum_root, max_chars=100)
        result = source.enrich(_packet(), _task(), "test")
        assert len(result.project_rules) == 100


class TestMemorySource:
    def test_search_finds_matches(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = MemoryStore(root)
        store.write("decisions", "- Use JWT for auth tokens\n- Use bcrypt for passwords\n")

        source = MemorySource(store)
        packet = _packet(goal="auth tokens")
        result = source.enrich(packet, _task(), "test")
        assert "JWT" in result.memory_context
        assert any("decisions" in p for p in result.pointers)

    def test_no_matches(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = MemoryStore(root)

        source = MemorySource(store)
        result = source.enrich(_packet(goal="nothing relevant"), _task(), "test")
        assert result.memory_context == ""

    def test_empty_goal(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = MemoryStore(root)

        source = MemorySource(store)
        result = source.enrich(_packet(goal=""), _task(title=""), "test")
        assert result.memory_context == ""


class TestHandoffSource:
    def test_loads_dependency_handoffs(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = TaskStore(root)
        store.ensure_project("test")

        # Create a completed dep with handoff
        dep = store.create_task("test", "Setup DB")
        store.update_task(
            "test",
            dep.id,
            status=TaskStatus.DONE,
            structured_handoff=AgentHandoffRecord(
                agent_id="claude",
                completed=["Schema created", "Migrations run"],
                gotchas=["Postgres 16 required"],
                decisions=["Use UUID primary keys"],
            ),
        )

        task = _task()
        task.depends_on = [dep.id]

        source = HandoffSource(store)
        result = source.enrich(_packet(), task, "test")
        assert "Schema created" in result.dependency_outputs
        assert "Postgres 16" in result.dependency_outputs
        assert any(dep.id in p for p in result.pointers)

    def test_no_dependencies(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = TaskStore(root)

        source = HandoffSource(store)
        result = source.enrich(_packet(), _task(), "test")
        assert result.dependency_outputs == ""

    def test_dep_not_done(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = TaskStore(root)
        store.ensure_project("test")
        dep = store.create_task("test", "Pending task")

        task = _task()
        task.depends_on = [dep.id]

        source = HandoffSource(store)
        result = source.enrich(_packet(), task, "test")
        assert result.dependency_outputs == ""


class TestReviewHistorySource:
    def test_extracts_review_failures(self):
        task = _task()
        task.progress = [
            ProgressEntry(
                timestamp=datetime(2026, 3, 29, tzinfo=UTC),
                agent="reviewer",
                message="Review FAILED (spec): Missing error handling",
            ),
            ProgressEntry(
                timestamp=datetime(2026, 3, 29, 1, tzinfo=UTC),
                agent="dev",
                message="Fixed error handling",
            ),
        ]

        source = ReviewHistorySource()
        result = source.enrich(_packet(), task, "test")
        assert "Review FAILED" in result.review_history
        assert "Missing error handling" in result.review_history
        # Non-failure entries excluded
        assert "Fixed error handling" not in result.review_history

    def test_no_failures(self):
        task = _task()
        task.progress = [
            ProgressEntry(
                timestamp=datetime(2026, 3, 29, tzinfo=UTC),
                agent="dev",
                message="Task completed successfully",
            ),
        ]

        source = ReviewHistorySource()
        result = source.enrich(_packet(), task, "test")
        assert result.review_history == ""

    def test_empty_progress(self):
        source = ReviewHistorySource()
        result = source.enrich(_packet(), _task(), "test")
        assert result.review_history == ""


class TestExternalReferencesSource:
    def test_adds_pointers(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = ProjectStore(root)
        store.create_project("test")
        store.update_policy(
            "test",
            external_references=[
                ExternalReference(name="Obsidian", path_or_url="/home/user/Vault/auth.md"),
                ExternalReference(name="Wiki", path_or_url="https://wiki.example.com/auth"),
            ],
        )

        source = ExternalReferencesSource(store)
        result = source.enrich(_packet(), _task(), "test")
        assert any("Obsidian" in p for p in result.pointers)
        assert any("wiki.example.com" in p for p in result.pointers)

    def test_no_references(self, tmp_path):
        root = tmp_path / ".agendum"
        root.mkdir()
        store = ProjectStore(root)
        store.create_project("test")

        source = ExternalReferencesSource(store)
        result = source.enrich(_packet(), _task(), "test")
        assert result.pointers == []
