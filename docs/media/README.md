# Diagram system

Every diagram in this directory is **hand-authored SVG**, rendered to PNG for
publication and visually inspected before it ships. This file documents the
method so the next diagram looks like it belongs to the same family.

## Why hand-written SVG

Not Mermaid, draw.io, Excalidraw or a screenshot of a whiteboard.

| Reason | Consequence |
|---|---|
| Total compositional control | Nested planes, a governance layer drawn *inside* the runtime box, a legend aligned to a specific edge — layout choices a graph-layout engine will not make |
| Real, selectable text | Searchable, translatable, and readable by screen readers rather than baked into pixels |
| Diffable in git | A one-line change to a label is a one-line diff, not a new binary blob |
| Zero dependencies | Anyone with a text editor can edit it; no account, no tool, no export step |
| Deterministic | The same source always produces the same image — no auto-layout drift between renders |

The cost is that nothing catches a mistake for you. That is what the loop below
is for.

## The loop that actually makes it work

Writing SVG blind produces overlapping text and misaligned arrows. The method is
**write → render → look → fix**, and the looking is not optional:

```bash
# 1. author or edit the SVG
# 2. render it to PNG (macOS Quick Look, no install needed)
qlmanage -t -s 2400 -o docs/media docs/media/<name>.svg
mv docs/media/<name>.svg.png docs/media/<name>.png
# 3. OPEN THE PNG AND LOOK AT IT — every pass, without exception
# 4. fix what the eye caught, re-render, look again
```

The first render of the architecture diagram had its per-stage annotations
overlapping into unreadable mush. Nothing in the source hinted at it; only the
render showed it. The fix was staggered annotation rows plus dotted leader
lines — a change that would never have been made without looking.

Render at `-s 2400` for anything going into a submission gallery: presentation
surfaces resample images and thin strokes disappear at small sizes.

## Visual system

Colours follow the Google Cloud palette, so the diagram reads as native to the
platform it runs on.

| Token | Hex | Meaning — used for nothing else |
|---|---|---|
| Blue | `#1a73e8` | Our own compute and surfaces (Cloud Run, the app, the console) |
| Blue wash | `#e8f0fe` | Background of an "ours" region |
| Green | `#188038` | Managed Google services we consume (Vertex, Firestore) |
| Green wash | `#e6f4ea` | Background of a managed-service region |
| Amber | `#f9ab00` | Event transport and ingestion (Cloud Storage, Pub/Sub) |
| Amber wash | `#fef7e0` | Background of a transport region |
| Red | `#d93025` | Governance, refusal, containment — anything that *stops* something |
| Red wash | `#fce8e6` | Background of a governance region |
| Purple | `#8430ce` | Human-facing surfaces, where a person appears |
| Grey | `#5f6368` / `#80868b` | Arrows, captions, secondary text |
| Ink | `#202124` / `#3c4043` | Primary text |

Type: Helvetica/Arial stack throughout. Title 27px bold, subtitle 14px, box
titles 14–16px bold, body 11.5–12.5px, captions 10.5–11px italic. Never below
10.5px — these are read on a projector and inside a video.

Shape grammar, applied consistently so shape carries meaning:

- **Rounded rect (`rx=10-12`)** — a system, service or region
- **Sharp rect (`rx=7`)** — a pipeline stage; stages sit in a row in execution order
- **Solid arrow** — data or control flow, direction is literal
- **Double-headed arrow** — a read/write relationship
- **Dashed grey line** — a temporal or logical link, not a data path ("the same people, minutes later")
- **Dotted vertical leader** — ties an annotation to the thing it annotates when they cannot touch

## Rules learned the hard way

1. **Annotations under a row of boxes must alternate rows.** Two lines of text
   under adjacent 76px-wide boxes will collide. Stagger them and add leaders.
2. **Give every region an explicit background.** A transparent region inherits
   whatever is behind it and the grouping stops reading.
3. **One idea per diagram.** If a box needs a paragraph, that paragraph is a
   different diagram.
4. **Label the arrows that are not obvious.** An unlabelled arrow between two
   boxes is a guess; `sync`, `push (OIDC)`, `notify` are facts.
5. **Put the numbers in.** Measured latency, cost and counts turn an
   architecture drawing into evidence. Only real measurements — never a number
   you have not seen come out of a run.
6. **Design for both light and dark presentation.** The background is painted
   explicitly white; text is dark ink. Never rely on the host's background.

## Files

Each diagram ships as a pair: `<name>.svg` (source of truth, edit this) and
`<name>.png` (2400px render for submissions and slides). See the index below.
