"""MCP entry points for implementers and separately launched administrators."""

from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from sdd_engine import service

implementer = FastMCP("spec-tech-engine")
administrator = FastMCP("spec-tech-engine-config")


@implementer.tool()
def begin_task(
    workspace: str,
    spec: str,
    tier: str,
    target: str,
    target_files: list[str],
    model: str,
    context: list[str] | None = None,
) -> dict[str, object]:
    """Start an implementation run and return its hydrated agent prompt."""
    return service.begin_task(workspace, spec, tier, target, target_files, model, context)


@implementer.tool()
def submit(workspace: str, run_id: str, files: dict[str, object]) -> dict[str, object]:
    """Submit whole files and required metadata for a paused run."""
    return service.submit(workspace, run_id, files)


@implementer.tool()
def finish_task(workspace: str, run_id: str) -> dict[str, object]:
    """Finalize scope findings and restore the worktree if the run failed."""
    return service.finish_task(workspace, run_id)


@implementer.tool()
def get_run_report(workspace: str, run_id: str) -> dict[str, object]:
    """Read the run's prompt, validation diagnostics, and scope report."""
    return service.get_run_report(workspace, run_id)


@administrator.tool()
def configure_profile(workspace: str, target: str, profile: dict[str, object]) -> dict[str, object]:
    """Create a versioned native validation profile for one target."""
    return service.configure_profile(workspace, target, profile)


@administrator.tool()
def get_profile(workspace: str, target: str) -> dict[str, object]:
    """Read the active native validation profile."""
    return service.get_profile(workspace, target)


def main() -> None:
    """Run either the implementer or administrator MCP server over stdio."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin", action="store_true")
    arguments = parser.parse_args()
    (administrator if arguments.admin else implementer).run(transport="stdio")


if __name__ == "__main__":
    main()
