# C++

- Use the project's C++ standard, compiler flags, formatter, and style. Do not introduce features beyond the configured standard or reformat unrelated files.
- Make ownership explicit. Prefer automatic storage and RAII; use `std::unique_ptr` for sole dynamic ownership and `std::shared_ptr` only when ownership is genuinely shared. Avoid raw owning pointers.
- Keep headers self-contained and minimize dependencies. Put declarations and definitions where the project's conventions require; avoid unnecessary macros and global state.
- Prefer standard library containers, strings, and algorithms over manual memory management. Use views or references only while the underlying object remains alive.
- Preserve const correctness and distinguish borrowing from ownership in APIs. Avoid unnecessary copies, but do not sacrifice clarity for micro-optimizations.
- Check bounds and validate external input. Handle failure through the project's established error model; do not mix exception and status-code strategies casually.
- For concurrent code, document synchronization and object lifetimes. Use standard synchronization primitives and avoid unsynchronized shared mutable state.
- Add focused tests for behavior and edge cases. Build with the project's warnings; use sanitizers or static analysis for changed low-level code when available.
