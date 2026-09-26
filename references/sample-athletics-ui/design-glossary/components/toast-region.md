# toast-region

**One-line definition.** A `toast-region` is the app-shell live region that shows transient command feedback after a successful or recoverable action.

**Anatomy.** Fixed bottom-right `.toast-region` with one or more `.toast` messages, `aria-live="polite"` and `aria-atomic="true"`; `.toast` uses `--bg-elevated`, `--shadow-soft`, `--radius-lg`, and status-colour text/border.

**Usage.** Short command feedback such as add, edit, remove, restore, save, or undo completion. Durable validation errors, duplicate warnings, missing data, and instructions must remain inline on the owning screen.

**Variants.** Default success (green); `warning` (amber) for recoverable stale/expired feedback; `error` (red) only when paired with an inline error; `info` (blue) for neutral command feedback.

**States.** Hidden; visible; auto-dismissed. Toasts may be URL-triggered, but cleanup must remove replay parameters after display.

**Kitchen-sink anchor.** [#overlays](../../sample-athletics-ui-kitchen-sink.html#overlays)

**Do / Don't.**

- Do make toast copy specific enough to confirm what changed.
- Don't use a toast as the only place an operator can read an error or recovery instruction.
