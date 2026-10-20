"""MCP entry points for implementers and separately launched administrators."""

from __future__ import annotations

import argparse
from typing import NotRequired

from mcp.server.fastmcp import FastMCP
from pydantic import ConfigDict, with_config

# Pydantic requires this TypedDict before Python 3.12.
from typing_extensions import TypedDict

from sdd_engine import service
from sdd_engine.models import Target, Tier

implementer = FastMCP("spec-tech-engine")
administrator = FastMCP("spec-tech-engine-config")


# These shapes publish the `GenerationOutput` JSON Schema to MCP clients but check only
# structure. Content rules stay in the graph, which counts violations as repair attempts.
@with_config(ConfigDict(extra="forbid"))
class WorkspaceFileInput(TypedDict):
    """One whole file to write at an approved target path."""

    path: str
    content: str


@with_config(ConfigDict(extra="forbid"))
class ErrorHandlingMappingInput(TypedDict):
    """How one infrastructure failure becomes a domain error."""

    failure: str
    domain_exception: str
    treatment: str


@with_config(ConfigDict(extra="forbid"))
class SubmissionPayload(TypedDict):
    """Whole files plus the documentation and error-handling account for one round."""

    files: list[WorkspaceFileInput]
    documentation_metadata: str
    error_handling_mapping: list[ErrorHandlingMappingInput]
    no_failure_paths: NotRequired[bool]


@implementer.tool()
def begin_task(
    workspace: str,
    tier: Tier,
    target: Target,
    model: str,
    spec: str | None = None,
    spec_path: str | None = None,
    target_files: list[str] | None = None,
    context: list[str] | None = None,
) -> dict[str, object]:
    """Start an implementation run and return its hydrated agent prompt.

    Pass `spec_path` to bind the run to a spec committed at HEAD, or `spec` as inline text.
    The spec header must say `Status: ready`; its `Target files:` line, when present, may
    stand in for `target_files`.
    """
    return service.begin_task(
        workspace,
        tier=tier,
        target=target,
        model=model,
        spec=spec,
        spec_path=spec_path,
        target_files=target_files,
        context=context,
    )


@implementer.tool()
def submit(workspace: str, run_id: str, files: SubmissionPayload) -> dict[str, object]:
    """Submit whole files and required metadata for a paused run."""
    return service.submit(workspace, run_id, dict(files))


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
