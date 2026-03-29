"""Tests for context enrichment pipeline — Protocol, ContextEnricher, budget."""

from __future__ import annotations

from agendum.models import ContextPacket, Task, TaskStatus
from agendum.tools.orchestrator.enrichment import ContextEnricher, ContextSource


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
        enricher = ContextEnricher()
        enricher.register(_StubSource("a", "project_rules", "A"))
        enricher.register(_StubSource("b", "memory_context", "B"))

        original = _packet()
        result = enricher.enrich(original, _task(), "test")

        assert original.project_rules == ""
        assert original.memory_context == ""
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
        assert total <= 5500

    def test_empty_fields_not_truncated(self):
        enricher = ContextEnricher()
        result = enricher.enrich(_packet(), _task(), "test", max_context_chars=100)
        assert result.project_rules == ""
        assert result.memory_context == ""
