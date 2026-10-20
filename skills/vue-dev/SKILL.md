---
name: vue-dev
description: Use automatically for Vue application work in .vue single-file components and Vue-based JavaScript or TypeScript modules. Covers component design, reactivity, data loading, errors, accessibility, testing, and rendering performance.
---

# Vue development reference

Use this skill for Vue components, composables, and Vue rendering behavior. Apply it with `javascript-dev` for JavaScript and `typescript-dev` for TypeScript. Those language skills provide the underlying language, API, error, data-validation, testing, documentation, and tooling rules.

## Establish the Vue environment

- Read repository instructions and identify the Vue version, Options API or Composition API conventions, build tool, router, state store, rendering mode, styling system, component conventions, and test tools before editing.
- Follow the existing framework and data-loading boundaries. Do not add a competing router, state store, request, form, or component library when the project already has an established solution.
- Use the Composition API and `<script setup>` for new Vue 3 components unless the project has a consistent alternative. Preserve the established style when modifying existing components.
- Preserve component props, emitted events, routes, data contracts, and accessibility behavior unless the request calls for a change.

## Design components and state

- Organize components around cohesive UI responsibilities. Keep components understandable and avoid both monolithic components and excessive wrappers that obscure data flow.
- Keep templates declarative. Pass inputs through props and notify parents through declared events; do not mutate props or silently alter parent-owned state.
- Keep reusable stateful logic in focused composables. A composable should expose a deliberate return shape, document which values remain reactive, and clean up any watchers, subscriptions, or resources it creates.
- Give each piece of state one clear owner. Keep local state near its consumers, lift coordinated state to the nearest common owner, and use provide/inject or the configured store only for genuinely shared concerns.
- Store only the minimum state needed to represent the UI. Use `computed` for values derived from reactive state rather than duplicating them and keeping copies synchronized with watchers.
- Model loading, empty, success, and failure as distinct states instead of combinations of loosely related booleans. Use typed unions in TypeScript or documented domain states in JavaScript.
- Use stable, domain-based keys for `v-for` lists that can change. Do not use array positions as keys for insertions, removals, or reordered data.

## Use reactivity and watchers deliberately

- Use `ref` and `reactive` with a clear understanding of where `.value` is required and how nested values are tracked. Avoid destructuring reactive properties in ways that lose reactivity; use the appropriate ref conversion when independent reactive bindings are needed.
- Keep computed getters pure and side-effect free. Use watchers only for effects that respond to specific reactive changes, not to derive values that can be computed directly.
- Prefer `watch` when the source and trigger conditions should be explicit. Use `watchEffect` only when automatic dependency tracking makes the effect simpler and its dependencies remain clear.
- Clean up subscriptions, timers, and in-flight work created by a watcher. Prevent stale async results from overwriting newer state, and create watchers synchronously with the component when they should stop on unmount.
- Use watcher flush timing and deep watching only when the DOM timing or nested observation is required. Avoid synchronous or deep watchers on large or frequently mutated data without a measured need.
- Do not mutate reactive state during render or hide state transitions in lifecycle hooks. Make setup, cleanup, and unmount behavior explicit.

## Manage APIs and asynchronous data

- Keep API clients, authentication, retries, pagination, runtime validation, and transport error translation outside visual components. Use the framework's loaders, server functions, or configured data layer when available.
- Validate external payloads before rendering or storing them. JavaScript and TypeScript types do not validate network, storage, or environment data at runtime; follow the language skill for boundary parsing.
- Represent request states explicitly and provide usable loading, empty, success, and failure UI. Preserve stale data only when product behavior calls for it.
- Prevent stale requests from overwriting newer state. Use the framework or request layer's cancellation facilities, or `AbortController` where appropriate, and clean up work when reactive inputs change or a component unmounts.
- Keep secrets and server-only data out of client components and browser bundles. Respect the framework's server/client boundary and hydration model.

## Handle errors and forms as UI states

- Use Vue's configured component or application error handling for failures during component setup or rendering. Handle errors from event handlers, watchers, and asynchronous requests explicitly in the layer that owns the operation.
- Map infrastructure errors into safe, stable UI states. Provide a recovery action when appropriate and do not expose raw server errors or sensitive payloads to users.
- Preserve diagnostics through the project's error reporting path while keeping secrets and personal data out of logs.
- Build forms with semantic controls and labels. Associate validation messages with their fields, preserve values after recoverable failures, and distinguish client validation from server rejection.
- Use native HTML elements for their intended behavior. Do not replace links, buttons, inputs, or headings with clickable generic containers.

## Accessibility, rendering, and performance

- Use semantic HTML, accessible names, keyboard-operable controls, visible focus, and appropriate status/error announcements. Do not rely on color or visual position alone to convey state.
- Keep server-rendered output deterministic. Avoid browser-only globals during server rendering and handle hydration through the framework's supported patterns.
- Measure before adding memoization or changing reactivity depth. Keep props stable where it prevents unnecessary child updates and avoid deep reactive tracking for large immutable structures when a shallow or explicit update model fits.
- Profile initial load and update performance with the project's tools. Split route or feature code when it improves measured load behavior, and virtualize large lists when DOM volume is the bottleneck.
- Avoid unnecessary component abstractions in large repeated lists. Keep expensive work and blocking operations out of render and interaction-critical paths.

## Tests, docs, and checks

- Follow the colocated test structure required by `javascript-dev` or `typescript-dev`. Test rendered behavior through accessible roles, labels, text, and user interactions rather than component internals or implementation-specific reactive details.
- Cover loading, empty, success, validation, error, retry, cancellation, keyboard interaction, and state transitions relevant to the component. Use the configured Vue testing tools; avoid snapshots as the only behavior check.
- Document exported components, composables, props, events, and non-obvious behavior using the language skill's JSDoc or TSDoc conventions.
- Run the configured formatter, linter, component tests, and JavaScript checks or TypeScript/Vue type checks. Keep framework-specific lint rules enabled and treat warnings as blocking.

## Vue references

- [Reactivity Fundamentals](https://vuejs.org/guide/essentials/reactivity-fundamentals.html)
- [Watchers](https://vuejs.org/guide/essentials/watchers.html)
- [State Management](https://vuejs.org/guide/scaling-up/state-management.html)
- [Performance Best Practices](https://vuejs.org/guide/best-practices/performance.html)

