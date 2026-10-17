# ResistanceAI design system

One palette, one accent, semantic color for meaning. The app is a clinical
console: dense, quiet, typographic — no gradients, glows, glassmorphism, or
decorative elements.

## Tokens

| Token | Value | Use |
|---|---|---|
| `BG` | `#0f172a` | page background |
| `SURFACE` | `#1e293b` | cards, sidebar, metric panels |
| input inset | `#141f36` | text/select/textarea backgrounds |
| `BORDER` | `rgba(255,255,255,0.09)` | 1px hairlines only — no shadows |
| `TEXT` | `#f1f5f9` | primary text |
| `MUTED` | `#94a3b8` | secondary text, labels (AA vs BG) |
| `FAINT` | `#7d92ab` | tertiary/meta text, reference chart lines (AA vs BG) |
| `ACCENT` | `#3b82f6` | interactive accent for borders/fills/focus/chart lines |
| `ACCENT_TXT` | `#60a5fa` | accent rendered as text on dark surfaces (AA ≥4.5) |
| `POS` | `#10b981` | sensitivity signals, low risk, protective attributions |
| `WARN` | `#f59e0b` | moderate risk, notices, resistance notes |
| `NEG` | `#f87171` | high risk, resistance mechanisms, risk-raising attributions |
| `RADIUS` | `6px` | every surface (tags use 4px) |

`.streamlit/config.toml` mirrors BG/SURFACE/ACCENT/TEXT so native Streamlit
widgets and custom HTML share the palette.

## Type

- **Inter** 400/500/600/700 — all UI text. Section labels use the
  `.eyebrow` style (0.66rem, 700, +0.16em tracking, uppercase, MUTED).
- **IBM Plex Mono** 400/500/600 — numeric readouts, metric values, masthead
  metadata. The "lab instrument" voice for data.

## Components

- **Hero readout** (`Risk summary`): the risk estimate is the focal point —
  large mono numeral + tier tag + ensemble interval + a segmented `risktrack`
  bar (ticks at the 40/70 tier boundaries). Secondary stats sit in a
  `.statrow` beneath. No duplicate gauge/metric cards.
- **Cards** (`.card`): uniform 1px border, 6px radius, no color bars or
  fills. Meaning is carried by `.tag` chips (bordered, colored text only)
  and body copy — sensitivity vs resistance is a `pos`/`neg` tag, not a
  colored panel.
- **Tags** (`.tag`): bordered text chips, transparent background.
  `acc` = evidence tier, plain = metadata, `pos`/`neg`/`warn` = semantics.
- **Metrics** (`stMetric`): MUTED uppercase label + mono value on SURFACE.
- **Empty state** (`.empty`): dashed outline, numbered next steps — always
  tells the user what to do.
- **Notice** (`.notice`): subdued amber regulatory strip at the top.

## States & motion

- `:focus-visible` — 2px ACCENT outline on all interactive elements.
- Hover — border moves to ACCENT, text to ACCENT_TXT; no background shifts.
- Active — subtle ACCENT fill (8%) on press.
- Disabled — 45% opacity.
- `@media (prefers-reduced-motion: reduce)` — all transitions/animations off.
- Loading — `st.spinner` with concrete copy ("Searching ClinicalTrials.gov…").
- Errors — `st.error`/`st.warning` with the actual cause and remediation.

## Layout

- `layout="wide"`; columns stack natively under Streamlit's 640px breakpoint.
- Media query at 640px: masthead stacks, hero/statrow compress, empty state
  narrows. Minimum 40px touch targets on buttons.
- One focal point per screen: Risk summary → hero readout; other tabs →
  section content with eyebrow labels, no competing decoration.
