"""Agent management tools: register, heartbeat, list, suggest routing."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agendum.models import Agent, AgentPersistenceRecord
from agendum.tools.orchestrator._helpers import resolve_model

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP, stores: Any, agents: dict[str, Agent]) -> None:
    """Register agent tools on the MCP server."""

    @mcp.tool()
    def pm_agent_register(
        agent_id: str,
        agent_type: str = "unknown",
        capabilities: str = "",
        model: str | None = None,
    ) -> str:
        """Register an agent identity with its capabilities.

        Agent registrations are persisted to disk so they survive server restarts
        and are visible across sessions on other devices.
        Capabilities should be comma-separated (e.g., "code,test,review").
        """
        caps = [c.strip() for c in capabilities.split(",") if c.strip()] if capabilities else []
        agent = Agent(
            id=agent_id,
            type=agent_type,
            capabilities=caps,
            model=model,
        )
        agents[agent_id] = agent

        # Persist to disk — load existing to increment session_count
        existing = stores.agent_store.load(agent_id)
        record = AgentPersistenceRecord(
            id=agent_id,
            type=agent_type,
            capabilities=caps,
            model=model,
            started=agent.started,
            last_seen=datetime.now(UTC),
            session_count=(existing.session_count + 1) if existing else 1,
        )
        stores.agent_store.save(record)

        return f"Registered agent '{agent_id}' ({agent_type}). Capabilities: {caps}"

    @mcp.tool()
    def pm_agent_heartbeat(agent_id: str) -> str:
        """Signal that an agent is still actively working. Call periodically during long tasks."""
        if agent_id not in agents:
            return f"Agent '{agent_id}' not registered. Use pm_agent_register first."
        agents[agent_id].last_seen = datetime.now(UTC)
        agents[agent_id].status = "active"

        # Persist updated last_seen
        existing = stores.agent_store.load(agent_id)
        if existing:
            existing.last_seen = datetime.now(UTC)
            existing.last_task = agents[agent_id].last_task
            stores.agent_store.save(existing)

        return f"Heartbeat recorded for '{agent_id}'."

    @mcp.tool()
    def pm_agent_list() -> str:
        """List all registered agents, including those from previous sessions.

        Active agents (current session) are shown with their current status.
        Agents from previous sessions that are not in the current registry are shown
        as 'disconnected' — useful for cross-device handoff visibility.
        """
        lines = []

        # Current-session agents
        for a in agents.values():
            task_str = f" working on {a.last_task}" if a.last_task else ""
            lines.append(f"  {a.id} ({a.type}) — {a.status}{task_str} [this session]")

        # Disk agents from previous sessions
        disk_agents = stores.agent_store.list_agents()
        active_ids = set(agents.keys())
        for rec in disk_agents:
            if rec.id not in active_ids:
                last = rec.last_seen.strftime("%Y-%m-%d %H:%M")
                task_str = f", last task: {rec.last_task}" if rec.last_task else ""
                lines.append(
                    f"  {rec.id} ({rec.type}) — disconnected, last seen {last}{task_str} [session {rec.session_count}]"
                )

        if not lines:
            return "No agents registered."

        return "Registered agents:\n" + "\n".join(lines)

    @mcp.tool()
    def pm_agent_suggest(project: str, task_id: str) -> str:
        """Suggest which agent/model category should handle a task based on its type.

        Uses the task's type field to recommend an appropriate agent category.
        Categories: code-complex, code-simple, code-frontend, planning, review,
        docs, email, research, personal.
        """
        try:
            task = stores.task.get_task(project, task_id)
        except ValueError as e:
            return f"Error: {e}"
        if not task:
            return f"Error: task '{task_id}' not found."

        # Guidance per task type (model-name-free — tiers come from policy).
        type_guidance = {
            "dev": "Use a capable model for architecture; fast tier for simple fixes",
            "docs": "Documentation tasks — fast tier is usually sufficient",
            "email": "Email drafts — fast tier",
            "planning": "Specs and architecture — use the most capable tier",
            "research": "Agent with web search access recommended",
            "review": "Use a DIFFERENT model than the one that wrote the code",
            "personal": "Any available agent",
            "ops": "Infrastructure and ops — use a capable tier",
        }

        task_type = task.type.value
        category = task.category.value if task.category else "unscored"
        guidance = type_guidance.get(task_type, "Any capable agent")

        policy = stores.project.get_policy(project)
        recommended = resolve_model(policy, task)

        lines = [
            f"Task: {task.id} ({task.title})",
            f"Type: {task_type} | Category: {category}",
        ]
        if recommended:
            lines.append(f"Recommended model: {recommended}")
        lines.append(f"Guidance: {guidance}")
        return "\n".join(lines)
