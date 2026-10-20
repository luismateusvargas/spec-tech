---
name: react-dev
description: Use automatically for React work in JSX or TSX applications, including component architecture, hooks, state, data loading, rendering, accessibility, testing, and performance. Apply with javascript-dev or typescript-dev according to the source language.
---

# React development reference

Use this skill for React components, Hooks, and React rendering behavior. Apply it with `javascript-dev` for JavaScript/JSX and `typescript-dev` for TypeScript/TSX. Those language skills provide the underlying language, API, error, testing, documentation, and tooling rules.

## Establish the React environment

- Read repository instructions and identify the React version, rendering mode, framework, router, data-fetching layer, styling system, component conventions, and test tools before editing.
- Follow the framework's server/client component and data-loading boundaries. Do not add a competing state, router, form, or request library when the project already has an established solution.
- Preserve public component props, routes, data contracts, and accessibility behavior unless the request calls for a change.

## Design components and state

- Build components around cohesive UI responsibilities. Keep components small enough to understand, but do not split them into fragments that obscure the user-facing structure.
- Keep rendering pure: for identical props, state, and context, return the same UI without mutating inputs or causing external side effects. Do not access browser globals or perform I/O during render.
- Pass data and event handlers through explicit props. Use composition and slots/children for flexible UI; avoid oversized components with many unrelated boolean props.
- Give each piece of state one clear owner. Keep local state near its consumer; lift shared state to the closest common owner. Use context for genuinely cross-cutting state, not as a default replacement for explicit props or a data store.
- Store the minimum state needed to represent the UI. Derive values from props and existing state during render instead of duplicating them in state and synchronizing them with Effects.
- Use controlled inputs when the parent must own or coordinate their values. Keep uncontrolled inputs where local browser form state is sufficient; make the choice deliberate.
- Use reducers when a related set of transitions becomes clearer as explicit actions. Model loading, empty, success, and failure as distinct states rather than combinations of loosely related booleans.
- Use stable keys that identify rendered items across insertions, deletions, and reordering. Do not use array positions as keys for mutable lists.

## Use Hooks and Effects correctly

- Call Hooks only at the top level of function components or custom Hooks, in the same order on every render. Name custom Hooks with the `use` prefix and keep each hook focused on reusable stateful behavior.
- Use event handlers for work caused by a user action. Use Effects only to synchronize with systems outside React, such as subscriptions, timers, browser APIs, or imperative third-party widgets.
- Every Effect that acquires a resource or subscribes must clean it up. Include every reactive value used by the Effect and satisfy the project's Hooks lint rules; do not suppress dependency warnings to force a desired execution schedule.
- Do not use Effects to derive render data, mirror props into state, or sequence application data flow. Prefer direct calculations, event handlers, framework loaders, or the established query/data layer.
- Assume Effects may be set up, cleaned up, and set up again in development. Make setup and cleanup symmetric and safe to repeat.
- Use refs for DOM handles or mutable values that do not determine rendered output. Do not use refs to hide state changes from React.

## Manage APIs and asynchronous data

- Keep API clients, validation, authentication, retries, and transport error translation outside visual components. Use framework loaders, server functions, or the configured data layer when available.
- Validate external payloads at runtime before rendering or storing them. Language types and component prop types do not validate network or storage data; follow `javascript-dev` or `typescript-dev` for boundary validation.
- Represent request states explicitly and provide usable loading, empty, success, and failure UI. Preserve stale data only when the product behavior calls for it.
- Prevent stale requests from overwriting newer state. Use the framework's cancellation or request lifecycle facilities, or `AbortController` where appropriate, and clean up on unmount or when request inputs change.
- Do not put secrets in client components, browser bundles, or client-side errors. Keep server-only credentials and data behind the server boundary.
- Avoid fetching from an Effect when the framework or existing data layer provides a better lifecycle, caching, or server-rendering integration.

## Treat errors and forms as UI states

- Use Error Boundaries at meaningful UI recovery boundaries for errors thrown while rendering descendants. Do not rely on an Error Boundary to catch event-handler failures, ordinary asynchronous request rejections, or server-rendering failures.
- Handle event and request failures explicitly in their owning layer, map them to safe UI states, and provide a retry or recovery action when appropriate. Do not expose raw provider errors or sensitive payloads to users.
- Preserve useful diagnostics through the project's error reporting path while keeping credentials and personal data out of logs.
- Build forms with semantic controls and labels. Associate validation messages with their fields, preserve entered values after recoverable errors, and distinguish client-side validation from server rejection.
- Use native HTML elements for their intended behavior. Do not replace links, buttons, form controls, or headings with clickable generic containers.

## Accessibility, rendering, and performance

- Use semantic HTML, accessible names, keyboard-operable controls, visible focus, and appropriate status/error announcements. Do not rely on color or visual position alone to convey state.
- Keep server-rendered output deterministic. Avoid depending on browser-only state during the initial server render; handle hydration boundaries through the framework's supported patterns.
- Measure before adding `memo`, `useMemo`, or `useCallback`. First keep state local, remove redundant work, and use stable list keys. Optimize based on React Profiler or equivalent measurements.
- For large collections, use the project's established virtualization or windowing approach when profiling shows rendering cost. Keep expensive work and blocking operations out of render and interaction-critical paths.

## Tests, docs, and checks

- Follow the colocated test structure required by `javascript-dev` or `typescript-dev`. Test rendered behavior through user-visible roles, labels, text, and interactions rather than component internals or Hook implementation details.
- Cover loading, empty, success, validation, error, retry, cancellation, keyboard interaction, and state transitions that matter to the component. Use the configured testing library and avoid snapshots as the only behavior check.
- Document exported components, Hooks, props, and non-obvious behavior using the language skill's JSDoc or TSDoc conventions.
- Run the configured formatter, linter, component tests, and JavaScript checks or TypeScript type checks. Keep the React Hooks lint rules enabled and treat warnings as blocking.

## React references

- [Keeping Components Pure](https://react.dev/reference/rules/components-and-hooks-must-be-pure)
- [Sharing State Between Components](https://react.dev/learn/sharing-state-between-components)
- [You Might Not Need an Effect](https://react.dev/learn/you-might-not-need-an-effect)
- [useEffect](https://react.dev/reference/react/useEffect)
- [Error Boundaries](https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary)

