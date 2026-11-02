---
name: angular-project-template
description: 'Use when generating or updating Angular code in this repository. Follows the repo''s Angular v22 conventions: standalone components, signals, native control flow, reactive forms, and accessible UI.'
---

# Angular Project Template

## When to use
- Creating a new feature, page, component, service, or route.
- Updating existing Angular UI, routing, or form flows.
- Refactoring code to match the project conventions.

## Inputs
- Feature goal and expected user flow.
- Files or route area to update.
- Data sources, state shape, and validation rules.
- Accessibility and UX constraints.

## Workflow
1. Inspect the existing structure under `src/app`.
2. Reuse current patterns before introducing new abstractions.
3. Prefer standalone components and `inject()` for services.
4. Model local state with signals and derived state with `computed()`.
5. Use native control flow in templates (`@if`, `@for`, `@switch`).
6. Keep feature routes lazy-loaded when adding new areas.

## Rules
- Do not add NgModules for new code.
- Do not use `@HostBinding` or `@HostListener`.
- Do not use `ngClass` or `ngStyle`; use class and style bindings instead.
- Prefer reactive forms or signal forms for new form work.
- Use `NgOptimizedImage` for static images.
- Keep UI accessible and WCAG AA compliant.

## Output
- Updated Angular source files.
- A short summary of what changed and why.
