# src/ui — token-driven component kit

General-purpose building blocks (`Button`, `Card`, `Select`, `Alert`) for any
future feature UI in this app. Adopt whichever ones fit the situation —
they're independent, not a framework you must fully commit to.

## Rule

Every component here reads colors/spacing/radius only via `var(--token)`
from `../styles/tokens.css` — never a hardcoded hex/px value. That's what
makes "swap the design concept" a one-file change:

1. Replace `src/styles/tokens.css` with a different
   `open-design/design-systems/<slug>/tokens.css` (same custom-property
   names, different values).
2. Every component in this folder re-skins automatically. No component code
   changes.

## When to reach for one of these vs. plain markup

- **Button**: any clickable action that isn't a bare icon-only control.
- **Card**: any grouped block of content that should read as "one unit"
  (a preview, a result summary, a settings section).
- **Select**: any `<select>` — the label wrapping already satisfies
  `getByLabelText` in tests with zero `id`/`htmlFor` plumbing.
- **Alert**: any user-facing status/error banner. `tone` picks
  danger/success/warn; defaults to `role="alert"` for screen readers.

Adding a new one later: keep the same contract (props extend the native
HTML element's props, styling lives in a co-located `.css` file, only
`var(--token)` references). Don't add a component here for something used
in exactly one place — that's premature; inline it in the feature first.
