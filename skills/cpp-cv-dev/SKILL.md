---
name: cpp-cv-dev
description: Use automatically for C++ computer vision, perception, image, and tensor pipeline work. Supplements cpp-dev with high-throughput API, frame-layout, alignment, SIMD, and allocation guidance.
---

# C++ computer vision development

Apply this skill together with `cpp-dev` for computer vision and perception code. Keep its rules focused on frame and tensor pipelines; `cpp-dev` supplies the general C++ ownership, error, documentation, and quality rules.

## Interfaces and pipeline services

- Keep vision services independent of other services. Inject infrastructure through small processing interfaces; do not create direct service-to-service dependencies.
- Use C++20 concepts to constrain processing interfaces and statically check capabilities without virtual dispatch in throughput-critical processing. Verify the configured target supports C++20; do not silently raise a project's language standard.
- Keep a processing service to at most one infrastructure template parameter. Leave constructors unconstrained and place concept requirements on the processing methods that need them.
- Use `std::shared_ptr<T>` for background execution dependencies that are genuinely shared across workers. A thread-safe reference count does not make the pointed-to object thread-safe; synchronize its state explicitly and document its lifetime.
- Design APIs around batches, views, and reusable buffers where the caller owns storage. Do not expose raw matrix pointers without their extent, layout, and lifetime contract.

## Validate frame and tensor data

- Validate image or tensor dimensions, channel counts, element type, row and plane strides, alignment requirements, and backing-storage length at pipeline boundaries.
- Use overflow-safe size calculations before allocating or indexing. Distinguish byte strides from element strides and support non-contiguous inputs when the API permits them.
- Use strong types for camera, stream, channel, pixel-format, and tensor identifiers when their values must not be mixed. Reject unsupported formats explicitly; do not reinterpret memory based on an unchecked enum or integer.
- Keep an empty or unavailable frame distinct from a failed frame. Do not turn processing errors into a blank image without an explicit downstream contract.

## Optimize memory and throughput

- Keep per-frame hot paths allocation-free by reusing caller-owned or pipeline-owned buffers. Reserve capacity at setup time and make buffer ownership explicit.
- Arrange bulk per-pixel or per-feature data in Structure of Arrays (SoA) form when processing consumes fields in parallel. Preserve an alternative layout when the measured access pattern or public representation makes it more efficient; justify the choice with profiling.
- Align data when the selected SIMD operation requires it. Use aligned loads only when the alignment guarantee is established; otherwise use safe unaligned operations or validate and copy at a deliberate boundary.
- Respect row and plane strides in every kernel. Avoid hidden image copies and repeated format conversions; make unavoidable conversions explicit and measure them.
- Optimize for cache locality and memory bandwidth using profiling and representative frame sizes. Do not infer performance from source layout alone.
- Keep exceptions and dynamic dispatch out of the frame-processing hot path. Use the configured explicit result/status type and a clear fallback policy; report failures outside the hot loop without allocating per pixel.

## Verify pipeline behavior and performance

- Add tests for contiguous and non-contiguous frames, unusual strides, alignment boundaries, unsupported formats, dimensions near overflow limits, and failure handling as relevant.
- Compare complete output frames or tensors when practical. Include fixtures that exercise both aligned and unaligned data.
- Verify hot-path allocation and throughput claims with the project's allocator or benchmark instrumentation and representative inputs. Keep correctness tests deterministic and separate from timing thresholds that are sensitive to the host.
- Run the foundational C++ formatter, compiler warning, test, and static-analysis checks from `cpp-dev`, plus configured SIMD, sanitizer, or benchmark checks affected by the change.

