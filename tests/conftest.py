"""Small reusable fixtures for engine contract and validation tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sdd_engine.models import CommandResult
from sdd_engine.validation import CommandSpec, ValidationProfile

TARGET_FILE = "pkg/module.py"


def generation_args(**overrides: object) -> dict[str, object]:
    """Return a valid JSON-shaped implementer submission."""
    args: dict[str, object] = {
        "files": [{"path": TARGET_FILE, "content": "VALUE = 1\n"}],
        "documentation_metadata": "# Arguments\nNone.\n\n# Errors\nNone.",
        "error_handling_mapping": [
            {
                "failure": "OSError while reading",
                "domain_exception": "StorageError",
                "treatment": "Wrap and re-raise with the path.",
            }
        ],
    }
    args.update(overrides)
    return args


@dataclass
class ScriptedRunner:
    """Command runner that returns scripted results or errors in order."""

    outcomes: list[CommandResult | Exception] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def run(
        self, command: CommandSpec, workspace: Path, profile: ValidationProfile
    ) -> CommandResult:
        """Run the next scripted command outcome."""
        self.calls.append(command.name)
        if not self.outcomes:
            return CommandResult(command_name=command.name, exit_code=0)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
