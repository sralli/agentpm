"""Onboarding guide — step-based setup for agendum."""

from __future__ import annotations

from pathlib import Path

from agendum.config import find_git_root

_VALID_MODES = ("always", "guided", "available")

_USAGE_RULES = {
    "always": (
        "MUST call `pm_status` at every session start. "
        "Use `pm_next`/`pm_done` for ALL task creation and completion. "
        "Log all decisions via `pm_done` and insights via `pm_learn`."
    ),
    "guided": (
        "Call `pm_status` at session start to check for active work. "
        "Use `pm_next`/`pm_done` for multi-file features and complex tasks. "
        "Skip for single-line fixes, version bumps, and pure research."
    ),
    "available": (
        "agendum is available for task tracking when needed. "
        "Use `pm_status` to check board state. "
        "Use `pm_next`/`pm_done` when working on tracked tasks."
    ),
}

_AGENDUM_SECTION_MARKER = "## agendum usage rules"

_SNIPPET_TEMPLATE = """\
## agendum usage rules

{usage_rules}

### Workflow
1. `pm_status` -- Orient: check current board state
2. `pm_next(project)` -- Get scoped, context-rich work package
3. Implement within scope and constraints
4. `pm_done(project, item_id)` -- Record completion with decisions/patterns
5. `pm_learn(content, tags)` -- Capture cross-project insights
"""

_FULL_TEMPLATE = """\
# {project_name}

{description}

{snippet}
### When to skip agendum
- Single-line fixes (typos, version bumps)
- Pure research/exploration (no code changes)

### Quick reference

```bash
{test_command}
{lint_command}
```

## Conventions

{conventions}
"""


def _parse_csv(value: str) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class OnboardingGuide:
    """Step-based onboarding guide consumed by both MCP tool and CLI."""

    def __init__(self, stores: object, git_root: Path | None = None):
        self._stores = stores
        self._git_root = git_root or find_git_root()

    def run_step(self, step: str, **kwargs) -> str:
        """Execute one onboarding step, return markdown with Next: hint."""
        handler = getattr(self, f"_step_{step}", None)
        if handler is None:
            valid = "start, usage_mode, project, learnings, rules, done"
            return f"Error: unknown step '{step}'. Valid steps: {valid}"
        try:
            return handler(**kwargs)
        except Exception as e:
            return f"Error in step '{step}': {e}"

    def _step_start(self, force: bool = False, **_kwargs) -> str:
        config = self._stores.project.read_config()  # type: ignore[union-attr]
        if config.onboarding.completed and not force:
            return (
                "Onboarding already completed.\n\n"
                f"Current usage mode: **{config.onboarding.usage_mode}**\n\n"
                "To re-run, call with `force=True`.\n\n"
                '> Next: pm_onboard(step="start", force=True) to re-run, or pm_status() to continue working'
            )

        return (
            "# Welcome to agendum!\n\n"
            "This guide will walk you through setting up agendum for your project.\n\n"
            "**Steps:**\n"
            "1. **usage_mode** -- Choose how agents should use agendum (always / guided / available)\n"
            "2. **project** -- Create your first project\n"
            "3. **learnings** -- Seed initial cross-project learnings\n"
            "4. **rules** -- Generate agent rules file (CLAUDE.md / AGENTS.md)\n"
            "5. **done** -- Finish setup\n\n"
            "Each step is optional -- skip any by moving to the next.\n\n"
            '> Next: pm_onboard(step="usage_mode", usage_mode="guided")\n'
            "> Options for usage_mode:\n"
            ">   - **always**: agents MUST use agendum for all tasks\n"
            ">   - **guided** (recommended): agents use agendum for complex tasks, skip for trivial ones\n"
            ">   - **available**: agendum is available but agents decide when to use it"
        )

    def _step_usage_mode(self, usage_mode: str = "", **_kwargs) -> str:
        if not usage_mode:
            return (
                "Error: usage_mode is required. Choose one of: always, guided, available\n\n"
                '> Next: pm_onboard(step="usage_mode", usage_mode="guided")'
            )

        mode = usage_mode.lower().strip()
        if mode not in _VALID_MODES:
            return (
                f"Error: invalid usage_mode '{usage_mode}'. Choose one of: always, guided, available\n\n"
                '> Next: pm_onboard(step="usage_mode", usage_mode="guided")'
            )

        config = self._stores.project.read_config()  # type: ignore[union-attr]
        config.onboarding.usage_mode = mode
        self._stores.project._write_config(config)  # type: ignore[union-attr]

        return (
            f"Usage mode set to **{mode}**.\n\n"
            f"Rule: {_USAGE_RULES[mode]}\n\n"
            '> Next: pm_onboard(step="project", project_name="my-project", project_description="...")'
        )

    def _step_project(self, project_name: str = "", project_description: str = "", **_kwargs) -> str:
        if not project_name:
            return (
                "Skipped project creation (no project_name provided).\n\n"
                '> Next: pm_onboard(step="learnings", seed_learnings="learning1, learning2")'
            )

        self._stores.project.create_project(project_name, project_description)  # type: ignore[union-attr]

        return (
            f"Project **{project_name}** created.\n\n"
            + (f"Description: {project_description}\n\n" if project_description else "")
            + '> Next: pm_onboard(step="learnings", seed_learnings="learning1, learning2") '
            + "or skip to rules step"
        )

    def _step_learnings(self, seed_learnings: str = "", **_kwargs) -> str:
        if not seed_learnings:
            return (
                "Skipped learnings seeding.\n\n"
                "Learnings capture cross-project insights. Use `pm_learn(content, tags)` anytime.\n\n"
                '> Next: pm_onboard(step="rules", test_command="...", lint_command="...", conventions="...")'
            )

        entries = _parse_csv(seed_learnings)
        added = []
        for entry in entries:
            learning_id = self._stores.learnings.add_learning(entry)  # type: ignore[union-attr]
            added.append(f"- {learning_id}: {entry}")

        return (
            f"Seeded **{len(added)}** learnings:\n"
            + "\n".join(added)
            + "\n\n"
            + '> Next: pm_onboard(step="rules", test_command="...", lint_command="...", conventions="...")'
        )

    def _step_rules(
        self,
        test_command: str = "",
        lint_command: str = "",
        conventions: str = "",
        **_kwargs,
    ) -> str:
        config = self._stores.project.read_config()  # type: ignore[union-attr]
        mode = config.onboarding.usage_mode
        usage_rules = _USAGE_RULES.get(mode, _USAGE_RULES["guided"])

        snippet = _SNIPPET_TEMPLATE.format(usage_rules=usage_rules)

        if not self._git_root:
            config.onboarding.rules_generated = True
            self._stores.project._write_config(config)  # type: ignore[union-attr]
            return (
                "Could not detect git root -- cannot write rules file.\n\n"
                "Here is the agendum rules snippet to add manually:\n\n"
                f"```markdown\n{snippet}```\n\n"
                '> Next: pm_onboard(step="done")'
            )

        # Check for existing rules file
        rules_path = None
        for filename in ("CLAUDE.md", "AGENTS.md"):
            candidate = self._git_root / filename
            if candidate.exists():
                rules_path = candidate
                break

        if rules_path:
            existing = rules_path.read_text(encoding="utf-8")
            if _AGENDUM_SECTION_MARKER in existing:
                config.onboarding.rules_generated = True
                self._stores.project._write_config(config)  # type: ignore[union-attr]
                return (
                    f"Agent rules file `{rules_path.name}` already contains agendum rules.\n\n"
                    '> Next: pm_onboard(step="done")'
                )
            # Append to existing file
            appended = existing.rstrip() + "\n\n" + snippet
            rules_path.write_text(appended, encoding="utf-8")
            config.onboarding.rules_generated = True
            self._stores.project._write_config(config)  # type: ignore[union-attr]
            return (
                f"Appended agendum rules to existing `{rules_path.name}`.\n\n"
                f"Your existing content was preserved.\n\n"
                '> Next: pm_onboard(step="done")'
            )

        # Create new CLAUDE.md from full template
        project_name = ""
        projects = self._stores.project.list_projects()  # type: ignore[union-attr]
        if projects:
            project_name = projects[0]

        full_content = _FULL_TEMPLATE.format(
            project_name=project_name or self._git_root.name,
            description="",
            snippet=snippet,
            test_command=test_command or "# uv run pytest",
            lint_command=lint_command or "# uv run ruff check .",
            conventions=conventions or "_Add project-specific conventions here._",
        )

        rules_path = self._git_root / "CLAUDE.md"
        rules_path.write_text(full_content, encoding="utf-8")
        config.onboarding.rules_generated = True
        self._stores.project._write_config(config)  # type: ignore[union-attr]

        return f'Generated `CLAUDE.md` at `{rules_path}`.\n\nUsage mode: **{mode}**\n\n> Next: pm_onboard(step="done")'

    def _step_done(self, **_kwargs) -> str:
        config = self._stores.project.read_config()  # type: ignore[union-attr]
        config.onboarding.completed = True
        self._stores.project._write_config(config)  # type: ignore[union-attr]

        mode = config.onboarding.usage_mode
        projects = self._stores.project.list_projects()  # type: ignore[union-attr]

        lines = [
            "# Onboarding complete!\n",
            f"**Usage mode:** {mode}",
            f"**Projects:** {', '.join(projects) if projects else 'none yet'}",
            f"**Rules generated:** {'yes' if config.onboarding.rules_generated else 'no'}",
            "",
            "## Next steps\n",
        ]

        if not projects:
            lines.append('1. Create a project: `pm_project("create", "my-project", "description")`')
        else:
            lines.append(f'1. Import a plan: `pm_ingest("{projects[0]}", "path/to/plan.md")`')
            lines.append(f'   Or add tasks: `pm_add("{projects[0]}", "task title")`')

        lines.extend(
            [
                '2. Get next work package: `pm_next("project-name")`',
                '3. Complete work: `pm_done("project-name", "item-id")`',
                '4. Capture insights: `pm_learn("what I learned", "tag1, tag2")`',
                "5. Check status anytime: `pm_status()`",
            ]
        )

        return "\n".join(lines)
