# Asterius Design System

A portable reference for anyone building a companion app that should look and feel
like Asterius (the ETF trading dashboard). Every value below is extracted directly
from the live app (`src/etf_terminal/frontend/css/app.css`), not invented — copy
these as-is rather than approximating them, so the two apps read as one family.

**Context:** Asterius is a dark-theme-only desktop trading terminal (PyWebView +
vanilla JS/CSS, no build step, no CDN dependencies — everything is vendored or
inlined so the packaged app works fully offline). If your app has the same
offline constraint, follow the same rule: no Google Fonts links, no CDN icon
kits — inline `@font-face` data URIs and vendor icon fonts locally.

---

## 1. Color

All colors are CSS custom properties on `:root`. Reference the variable, not the
hex, wherever possible — that's what lets a future palette tweak propagate.

```css
:root {
  /* Surfaces */
  --bg:          #0b0f19;   /* page background */
  --panel-top:   #111827;   /* card gradient start */
  --panel-bot:   #0f1422;   /* card gradient end */
  --deep:        #080c14;   /* recessed surfaces: inputs, buttons, track backgrounds */

  /* Borders */
  --border:      rgba(30, 41, 59, 0.9);
  --border-soft: rgba(30, 41, 59, 0.6);

  /* Text */
  --text:  #f1f5f9;   /* primary text */
  --muted: #94a3b8;   /* secondary text, card titles */
  --dim:   #64748b;   /* tertiary text, captions, sub-labels */
  --faint: #475569;   /* placeholder-level text, disabled icons */

  /* Accent */
  --cyan: #22d3ee;    /* THE accent — links, active states, focus rings, brand */

  /* Semantic (never used as the accent, always paired with meaning) */
  --emerald: #34d399; /* positive / up / buy / good */
  --red:     #f87171; /* negative / down / sell / bad */
  --amber:   #fbbf24; /* warning / demo-mode / caution */
  --indigo:  #818cf8; /* informational / secondary accent (rarely primary) */
  --purple:  #c084fc; /* a second informational accent, used sparingly for variety in card dots */

  --radius:    20px;  /* large cards */
  --radius-sm: 12px;  /* buttons, inputs, small cards, chips-as-pills use 999px */
}
```

**Usage rules, not just values:**
- `--cyan` is the *only* accent. Semantic colors (emerald/red/amber) are for state, never for branding or navigation — don't reach for green as a second "positive brand" color.
- Card backgrounds are always a subtle vertical gradient (`--panel-top` → `--panel-bot`), never a flat fill — this is what gives cards a slight lift.
- `--deep` is for anything *recessed*: text inputs, buttons at rest, progress-bar tracks, code/mono blocks.
- Borders are almost always 1px, using `--border` (stronger) or `--border-soft` (quieter, for internal dividers/secondary chrome).

### Light theme
Asterius itself is dark-only by deliberate choice (a trading terminal convention). If your companion app needs to support light mode, don't naively invert these — keep the same hue relationships:
- Background → a cool off-white with a faint blue-grey bias (e.g. `#f4f6fb`), not pure white.
- Cards → white with the same soft border color at higher opacity for contrast.
- `--cyan` accent should shift slightly darker/more saturated on light backgrounds (e.g. `#0891b2`) to maintain contrast — a light-background page needs a darker cyan than a dark-background one to read at the same visual weight.
- Semantic colors (emerald/red/amber) typically need to darken by one step on light backgrounds too, for the same contrast reason.

---

## 2. Typography

```css
--mono: "Cascadia Mono", Consolas, "SF Mono", Menlo, monospace;
--sans: "Segoe UI Variable Display", "Segoe UI", system-ui, -apple-system, sans-serif;
```

- **Sans** (`--sans`) is used for everything except numbers-that-line-up: headings, body copy, labels, buttons.
- **Mono** (`--mono`) is used specifically for *tabular/financial data* — prices, percentages, scores, any figure a user's eye needs to scan down a column. Always pair with `font-variant-numeric: tabular-nums` where digits stack in a table or list.
- Base body size is **14px**. The type scale in practice (extracted from real usage, not a designed scale — but consistent enough to reuse):

| Use | Size | Weight | Notes |
|---|---|---|---|
| Page/brand title (`h1`) | 17px | 700 | `letter-spacing: -0.02em` |
| Dashboard/section title | 22px | 800 | `letter-spacing: -0.02em` |
| Card title | 11px | 700 | uppercase, `letter-spacing: 0.12em`, color `--muted` |
| Card sub/caption | 11.5px | 400 | color `--dim`, `line-height: 1.5` |
| kv-label (field label above a value) | 9.5px | 800 | uppercase, `letter-spacing: 0.12em`, color `--dim` |
| kv-value (the value itself) | 15px | 700 | `--mono` |
| Big price display | 20–24px | 700–900 | `--mono` |
| Pill/badge text | 10px | 700 | uppercase, `letter-spacing: 0.08em` |
| Chip text | 9.5px | 700 | `--mono` |
| Body/default | 14px | 400 | |

Card titles and kv-labels are **always uppercase with wide letter-spacing** — this is the single most identifiable typographic signature of the app. A companion app that keeps this convention for its own field labels will feel instantly related, even with different content.

---

## 3. Core components

### Card
The fundamental content unit. Every widget, table, and panel lives in one.

```css
.card {
  background: linear-gradient(180deg, var(--panel-top), var(--panel-bot));
  border: 1px solid var(--border);
  border-radius: var(--radius);      /* 20px */
  padding: 18px 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.card-title {
  font-size: 11px; font-weight: 700; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--muted);
  display: flex; align-items: center; gap: 8px;
}
.card-title .dot { width: 8px; height: 8px; border-radius: 3px; }  /* colored status dot, one per card, color varies by category */
```

Smaller/nested cards (e.g. a widget rendered inside another panel) drop the radius to `--radius-sm` (12px) and often the shadow — reserve the full 20px radius + shadow combination for top-level cards only.

### Buttons
```css
.btn {
  background: var(--deep); border: 1px solid var(--border);
  padding: 8px 14px; border-radius: var(--radius-sm);
  font-weight: 600; transition: all 0.15s;
}
.btn:hover  { border-color: var(--cyan); color: var(--cyan); }
.btn.active { background: rgba(34, 211, 238, 0.12); border-color: rgba(34, 211, 238, 0.5); color: var(--cyan); }
```
Icon-only buttons (`.icon-btn`) are 34×34px, same border/hover treatment, centered icon, no visible label — used in the header and card corners.

### Inputs
```css
select, input[type="text"], input[type="number"] {
  background: var(--deep); border: 1px solid var(--border);
  border-radius: var(--radius-sm); padding: 8px 12px; outline: none;
}
input:focus, select:focus { border-color: rgba(34, 211, 238, 0.5); }
```
Focus state is border-color only — no glow/ring. Keep it that quiet.

### Pills (status badges)
Small, uppercase, rounded-full — used for connection state, mode flags (e.g. "Demo Data"), and action verdicts.
```css
.pill {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--border); color: var(--muted);
}
.pill.live  { color: var(--emerald); border-color: rgba(52,211,153,.35); background: rgba(52,211,153,.08); }
.pill.demo  { color: var(--amber);   border-color: rgba(251,191,36,.35); background: rgba(251,191,36,.08); }
```
Pattern: a semantic-colored pill is always `color` + matching `border-color` at ~35% opacity + matching `background` at ~8% opacity — never a solid fill.

### Chips (data tags)
Smaller and denser than pills, used for a strip of related mini-values (e.g. per-indicator vote scores).
```css
.chip {
  font-size: 9.5px; font-weight: 700; font-family: var(--mono);
  padding: 2.5px 8px; border-radius: 999px;
  background: rgba(148, 163, 184, 0.1); color: var(--muted);
  border: 1px solid var(--border-soft);
}
.chip.up   { background: rgba(52,211,153,.1);  color: var(--emerald); border-color: rgba(52,211,153,.25); }
.chip.down { background: rgba(248,113,113,.1); color: var(--red);     border-color: rgba(248,113,113,.25); }
```

### Action pill (buy/hold/sell style verdicts)
For a prominent single-word verdict (not a whole row of chips):
```css
.action-pill { font-size: 16px; font-weight: 900; letter-spacing: 0.08em; padding: 6px 22px; border-radius: 999px; }
.action-pill.buy  { background: rgba(52,211,153,.15); color: var(--emerald); border: 1px solid rgba(52,211,153,.4); }
.action-pill.sell { background: rgba(248,113,113,.15); color: var(--red);    border: 1px solid rgba(248,113,113,.4); }
.action-pill.hold { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; }
```
This is the one place a *neutral* state gets its own distinct treatment (slate, not grey-of-muted) rather than reusing `--dim`/`--faint` — worth copying exactly if your app has a similar tri-state verdict (e.g. a news-sentiment reader: bullish/neutral/bearish).

### Tables
Two sizes: `table.screener` (full data grid, roomier padding) and `table.mini` (12px, compact, used inside cards). Both share: no vertical borders, a `border-bottom` divider on rows, sticky `<thead>` on scrollable panels, uppercase 10px letter-spaced column headers in `--dim`.

### Scrollbars
```css
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--deep); }
::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: #334155; }
```
Custom scrollbars are used everywhere — an unstyled native scrollbar on a dark UI reads as unfinished.

---

## 4. Layout conventions

- **Header**: `sticky top:0`, 62px tall, `background: rgba(15,21,36,.92)` + `backdrop-filter: blur(8px)`, bottom border `--border`. Brand mark (icon + wordmark) left, controls right, a draggable zone between them in the desktop-shell build. **As of the two-pane redesign, the header is pure global chrome only** — connection-state pill, alerts bell, menu — it no longer carries any per-instrument data (price used to live here; it moved into the nav pane's base-view, see below). If your app has a similar "one thing is currently open" concept, keep that same split: header = app-level state, never content-level state.
- **Content grid**: a 12-column CSS grid (`gap: 18px`) for dashboard-style pages, collapsing every column to full-width under 1100px. Cards declare their own span (`col-3` through `col-12`).
- **Widget grid** (the ticker dashboard specifically): a denser 6-column grid with drag-to-reorder and per-card resize (2–6 cols × 1–2 rows), `grid-auto-rows` fixed at 205px.
- **Card interior spacing**: `gap: 12px` between a card's title/sub/body sections via flex column — never manual margins between them.
- **Border radius scale**: 20px (top-level cards) → 12px (buttons, inputs, nested cards) → 999px (pills/chips/badges). Nothing in between; don't introduce an 8px or 16px radius.

### The two-pane shell (shipped)
The app is now a persistent **two-pane shell** below the header: a fixed-width left nav pane and a flexible right content pane, both full-height (`calc(100vh - 62px)`).

```css
.app-shell { display: flex; align-items: stretch; height: calc(100vh - 62px); }
#nav-pane {
  width: 340px; flex-shrink: 0;
  background: var(--panel-bot); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;   /* children scroll internally */
}
main#content-pane { flex: 1; min-width: 0; overflow-y: auto; max-width: 1480px; margin: 0 auto; padding: 22px 24px 60px; }
```

**The nav pane has exactly two mutually-exclusive states**, toggled by swapping which child is `.hidden`:

1. **Browse mode** (default — nothing selected): a search box, then a scrollable list of rows. Two row types share one visual language — icon/star + label on the left, secondary data right-aligned:
   ```css
   .tick-row, .tool-row { display: flex; align-items: center; border-radius: var(--radius-sm); cursor: pointer; transition: background .12s; }
   .tick-row:hover, .tool-row:hover { background: rgba(148, 163, 184, 0.07); }
   .tool-row.active { background: rgba(34, 211, 238, 0.1); color: var(--cyan); }   /* the ONE place a nav item shows as "currently open" */
   ```
   `.tick-row` (a selectable list item — ticker/name left, price/change right, 12px/10px sizes) vs `.tool-row` (a simple nav link — icon + label, 12.5px, no secondary data). A news app's own sidebar (source list, saved-articles list, category nav) maps directly onto this pair: `.tick-row`-style rows for the list of things, `.tool-row`-style rows for navigation/tools below it.
2. **Base-view mode** (something's selected): a "back to browsing" link, then a header block (big title + secondary line + the promoted price display, see below), then a tabbed sub-nav (`.ii-tabs`/`.ii-tab`, small flex-wrapped pill tabs) over scrollable detail content. This is the generic "here's the one thing you picked, with tabs of detail" pattern — reusable for a news app's "selected article" or "selected source" panel.

**Content-pane empty state** (nothing selected, browse mode active) — a simple centered prompt, worth copying verbatim for any "pick something from the list" page:
```css
.content-empty {
  height: 100%; min-height: 320px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 10px; color: var(--dim); text-align: center;
}
.content-empty i { font-size: 34px; color: var(--faint); }   /* large, faint icon — never the accent color here */
.content-empty h3 { font-size: 14px; font-weight: 600; color: var(--muted); }
.content-empty p { font-size: 12px; max-width: 300px; line-height: 1.6; }
```

---

## 5. Icons

Font Awesome Free 6.7.2, **vendored locally** (`frontend/vendor/fontawesome/`) — solid + regular styles only, no brands, no CDN. If your app also uses Font Awesome, vendoring the same subset keeps icon weight/style visually identical; otherwise, match the *line weight and size* (icons are used at 14–16px, mostly `fa-solid`, occasionally `fa-regular` for less-emphasized actions) rather than mixing icon families.

---

## 6. Voice

Not a visual point, but part of the identity: copy is plain-English first, jargon only behind an ⓘ explainer with a Simple/Trader toggle. Card titles are human phrases ("Buying vs Selling Pressure"), not technical labels ("OBI"). If your companion app shares an audience with this one, keep that same register — plain-language headline, technical detail available on demand, never the reverse.
