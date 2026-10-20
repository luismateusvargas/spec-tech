---
name: cpp-aaa-dev
description: Use automatically for C++ AAA game engines, simulation systems, and real-time gameplay code. Supplements cpp-dev with deterministic state, ECS, frame-budget, cache-locality, and hot-loop allocation rules.
---

# C++ AAA game development

Apply this skill together with `cpp-dev` for game-engine, simulation, and real-time gameplay code. Keep frame-loop constraints on the runtime paths they affect; `cpp-dev` supplies the general C++ ownership, error, documentation, and quality rules.

## Model entities, state, and APIs

- Use `enum class` or explicit tagged states for actor, animation, and gameplay transitions. Make transitions exhaustive and keep transition rules in small, testable functions or systems.
- Wrap entity, actor, component, and resource identifiers in distinct lightweight handle types. Validate handle generation and ownership at system or API boundaries so stale or cross-domain IDs cannot silently refer to the wrong object.
- Prefer composition through components and systems. Follow the engine's ECS architecture; do not add a second entity model or duplicate systems for the same state.
- Keep public engine APIs stable, strongly typed, and explicit about object lifetime and thread ownership. Validate loaded assets and external input before they enter simulation state.

## Protect the frame loop

- Treat the game loop and other measured hot paths as frame-budgeted code. Set budgets from the target frame rate and profile on representative target hardware.
- Do not allocate or free heap memory in hot-loop systems. Preallocate bounded pools, arenas, or contiguous buffers during setup and reuse them during updates. Measure allocation counts in verification builds.
- Do not use virtual dispatch, `std::unique_ptr<Interface>`, or other runtime polymorphism inside hot-loop systems. Compose systems with templates, concrete types, or compile-time duck typing; keep dynamic dispatch at setup or other non-hot boundaries if the architecture needs it.
- Keep hot-path data cache-friendly and contiguous. Select AoS, SoA, or hybrid storage based on the component access pattern and measured results; do not convert layouts without evidence.
- Keep hot-loop error handling non-throwing and allocation-free. Use explicit status or result values and deterministic fallback or reset behavior. Route diagnostics through preallocated or deferred channels rather than formatting or logging on the frame thread.
- Avoid blocking I/O, unbounded work, and waits on locks in frame-loop systems. Bound queues and background work, and make overload behavior explicit.

## Preserve deterministic concurrency

- Make update order, task ownership, synchronization, and shutdown explicit. Use deterministic scheduling where simulation results depend on order.
- Use atomics only when their memory ordering and state protocol are correct. Prefer simpler synchronization when it meets the frame budget; do not use lock-free structures without a measured need and clear correctness argument.
- Avoid shared mutable state between systems when ownership or message passing is clearer. Ensure worker tasks cannot outlive their engine-owned resources.

## Verify correctness and frame budgets

- Test state transitions, handle validation, deterministic updates, and complete actor or entity results. Use fixtures and compare complete values or snapshots where practical.
- Keep tests off the live game-loop thread. Use deterministic clocks, schedulers, and seeded inputs for simulation tests.
- Verify allocation-free hot-path behavior with instrumentation and measure frame-time distributions on representative builds and hardware. Treat frame-time thresholds as target-specific and document the target.
- Run `cpp-dev` checks plus configured race, sanitizer, platform, engine, and performance checks affected by the change. Do not use a release build for routine verification; use target release or profiling builds when measuring final performance.

