The Remaining ~20–25% to Reach a Full Multi-Coding Platform

  To go from a single-spec worktree engine to a fully automated multi-stack platform, four layers remain:

  1. Macro-DAG / Multi-Spec Orchestrator (Stacking Runs into Waves):
      • Current state: One SddEngine run executes one spec + one Target + one worktree. A full-stack feature (postgresql schema → rust/diesel API → react-typescript UI) requires the caller to run three separate specs sequentially or across worktrees.
      • Next layer: A parent LangGraph (or Sota orchestrator) that ingests a dependency DAG of ready specs, automatically creates git worktree branches per spec, dispatches parallel implementer agents against sdd_engine, runs the reviewer gate, and merges approved worktrees
      in dependency order.
  2. Automated Project Toolchain Image Builder:
      • Current state: toolchains/ provides base images for Python, Rust, and Go. Because DockerCommandRunner enforces --network=none and --pull=never, projects with third-party dependencies (or Node/C++/DB targets) require an admin to pre-build a project image.
      • Next layer: An admin command that builds and pins a project-specific validation image from the repo's lockfiles (uv.lock, Cargo.lock, package-lock.json, CMakePresets.json) and registers its sha256 digest via configure_profile.
  3. Structured Patch / Rename / Delete Operations:
      • Current state: GenerationOutput.files replaces whole files (up to 1M chars) and does not express file deletions or renames.
      • Next layer: Supporting declared file deletions/renames and hunk/AST-level patches alongside whole-file replacement so agents can refactor large existing files with minimal token output.
  4. Asynchronous Validation & Streaming Telemetry:
      • Current state: submit blocks synchronously while Docker commands run (bounded by timeout_seconds=120 by default).
      • Next layer: Optional non-blocking background validation with MCP progress notifications or event streaming for long C++ (cpp-aaa) or integration test suites.