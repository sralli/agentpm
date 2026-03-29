"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from mcp.server.fastmcp import FastMCP

from agendum.server import _Stores
from agendum.store.plan_store import PlanStore
from agendum.store.trace_store import TraceStore
from agendum.tools import agent, board, memory, orchestrator, project, task, utils
from agendum.tools.orchestrator.enrichment import ContextEnricher
from agendum.tools.orchestrator.sources import (
    ExternalReferencesSource,
    HandoffSource,
    MemorySource,
    ProjectRulesSource,
    ReviewHistorySource,
)


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    """Create a temporary .agentpm root directory."""
    root = tmp_path / ".agentpm"
    root.mkdir()
    return root


@pytest_asyncio.fixture
async def mcp_server(tmp_path: Path):
    """Fresh FastMCP instance with isolated stores, wired for all tool modules."""
    root = tmp_path / ".agentpm"
    root.mkdir()

    stores = _Stores()
    stores._root = root  # bypass resolve_root()
    stores._plan = PlanStore(root)
    stores._trace = TraceStore(root)

    agents_registry: dict = {}

    # Build enricher with all sources
    enricher = ContextEnricher()
    enricher.register(ProjectRulesSource(root))
    enricher.register(MemorySource(stores.memory))
    enricher.register(HandoffSource(stores.task))
    enricher.register(ReviewHistorySource())
    enricher.register(ExternalReferencesSource(stores.project))

    mcp = FastMCP("agentpm-test")
    board.register(mcp, stores, agents_registry)
    project.register(mcp, stores, agents_registry)
    task.register(mcp, stores, agents_registry)
    memory.register(mcp, stores, agents_registry)
    agent.register(mcp, stores, agents_registry)
    utils.register(mcp, stores, agents_registry)
    orchestrator.register(mcp, stores, agents_registry, enricher)

    return mcp, stores, agents_registry


async def call(mcp: FastMCP, tool_name: str, **kwargs) -> str:
    """Call an MCP tool and return the text result."""
    content, _ = await mcp.call_tool(tool_name, kwargs)
    return content[0].text
