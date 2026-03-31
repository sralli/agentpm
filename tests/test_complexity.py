"""Tests for the heuristic complexity scorer."""

from __future__ import annotations

from agendum.complexity import score_complexity
from agendum.models import TaskCategory


class TestDirectMapping:
    """Non-dev/ops types map directly to their category."""

    def test_docs(self):
        assert score_complexity("Write API docs", task_type="docs") == TaskCategory.DOCS

    def test_email(self):
        assert score_complexity("Draft onboarding email", task_type="email") == TaskCategory.EMAIL

    def test_planning(self):
        assert score_complexity("Plan Q3 roadmap", task_type="planning") == TaskCategory.PLANNING

    def test_research(self):
        assert score_complexity("Research caching strategies", task_type="research") == TaskCategory.RESEARCH

    def test_review(self):
        assert score_complexity("Review PR #42", task_type="review") == TaskCategory.REVIEW

    def test_personal(self):
        assert score_complexity("Update dotfiles", task_type="personal") == TaskCategory.PERSONAL


class TestSimpleKeywords:
    """Simple keywords force CODE_SIMPLE regardless of other signals."""

    def test_typo(self):
        assert score_complexity("Fix typo in README", task_type="dev") == TaskCategory.CODE_SIMPLE

    def test_rename(self):
        assert score_complexity("Rename variable foo to bar", task_type="dev") == TaskCategory.CODE_SIMPLE

    def test_bump_version(self):
        assert score_complexity("Bump version to 2.0", task_type="dev") == TaskCategory.CODE_SIMPLE

    def test_fix_lint(self):
        assert score_complexity("Fix lint errors", task_type="dev") == TaskCategory.CODE_SIMPLE

    def test_formatting(self):
        assert score_complexity("Fix formatting issues", task_type="dev") == TaskCategory.CODE_SIMPLE

    def test_simple_overrides_other_signals(self):
        """Even with many files and criteria, simple keywords win."""
        result = score_complexity(
            "Fix typo in auth module",
            task_type="dev",
            priority="critical",
            key_files=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
            acceptance_criteria=["a", "b", "c", "d", "e", "f"],
        )
        assert result == TaskCategory.CODE_SIMPLE


class TestArchKeywords:
    """Architectural keywords push toward CODE_COMPLEX."""

    def test_refactor(self):
        result = score_complexity(
            "Refactor authentication module",
            task_type="dev",
            key_files=["auth.py", "middleware.py", "config.py"],
        )
        assert result == TaskCategory.CODE_COMPLEX

    def test_migrate(self):
        result = score_complexity("Migrate database schema to v3", task_type="dev")
        assert result in (TaskCategory.CODE_COMPLEX, TaskCategory.CODE_FRONTEND)

    def test_security(self):
        result = score_complexity(
            "Implement security hardening",
            task_type="dev",
            key_files=["auth.py", "crypto.py", "middleware.py", "config.py"],
        )
        assert result == TaskCategory.CODE_COMPLEX

    def test_arch_in_description(self):
        result = score_complexity(
            "Update module",
            description="Need to refactor the entire authentication layer",
            task_type="dev",
            key_files=["a.py", "b.py", "c.py"],
        )
        assert result == TaskCategory.CODE_COMPLEX


class TestFileCount:
    """Key files count affects scoring."""

    def test_no_files_low_score(self):
        result = score_complexity("Add a button", task_type="dev")
        assert result == TaskCategory.CODE_SIMPLE

    def test_many_files_high_score(self):
        result = score_complexity(
            "Update error handling",
            task_type="dev",
            priority="high",
            key_files=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py", "g.py"],
            acceptance_criteria=["handle all error types", "add tests", "update docs"],
        )
        assert result in (TaskCategory.CODE_COMPLEX, TaskCategory.CODE_FRONTEND)


class TestPriority:
    """Priority affects scoring."""

    def test_critical_with_files_pushes_complex(self):
        result = score_complexity(
            "Fix production outage",
            task_type="dev",
            priority="critical",
            key_files=["server.py", "handler.py", "db.py", "cache.py"],
            acceptance_criteria=["fix the bug", "add regression test", "update monitoring"],
        )
        assert result in (TaskCategory.CODE_COMPLEX, TaskCategory.CODE_FRONTEND)

    def test_low_priority_stays_simple(self):
        result = score_complexity("Add logging to helper", task_type="dev", priority="low")
        assert result == TaskCategory.CODE_SIMPLE


class TestDependencies:
    """Dependencies count affects scoring."""

    def test_many_deps(self):
        result = score_complexity(
            "Implement integration layer",
            task_type="dev",
            priority="high",
            depends_on=["task-1", "task-2", "task-3", "task-4"],
            key_files=["integration.py", "api.py", "models.py"],
            acceptance_criteria=["integrate with all services", "add error handling"],
        )
        assert result in (TaskCategory.CODE_COMPLEX, TaskCategory.CODE_FRONTEND)


class TestConstraints:
    """Constraints count affects scoring."""

    def test_many_constraints(self):
        result = score_complexity(
            "Build data pipeline",
            task_type="dev",
            priority="high",
            constraints=["must be backwards compatible", "no downtime", "under 100ms latency"],
            key_files=["pipeline.py", "transform.py", "loader.py"],
        )
        assert result in (TaskCategory.CODE_COMPLEX, TaskCategory.CODE_FRONTEND)


class TestOpsType:
    """Ops tasks use the same scoring as dev."""

    def test_simple_ops(self):
        result = score_complexity("Update Dockerfile base image", task_type="ops")
        assert result == TaskCategory.CODE_SIMPLE

    def test_complex_ops(self):
        result = score_complexity(
            "Migrate infrastructure to new provider",
            task_type="ops",
            priority="critical",
            key_files=["terraform/main.tf", "terraform/variables.tf", "terraform/outputs.tf", "ci.yaml"],
        )
        assert result == TaskCategory.CODE_COMPLEX


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_title(self):
        result = score_complexity("", task_type="dev")
        assert result == TaskCategory.CODE_SIMPLE

    def test_unknown_type_treated_as_dev(self):
        """Unknown types fall through to dev-style scoring."""
        result = score_complexity("Something", task_type="unknown")
        assert result == TaskCategory.CODE_SIMPLE

    def test_none_lists(self):
        """None values for optional lists don't crash."""
        result = score_complexity(
            "Add feature",
            task_type="dev",
            key_files=None,
            acceptance_criteria=None,
            depends_on=None,
            constraints=None,
        )
        assert isinstance(result, TaskCategory)
