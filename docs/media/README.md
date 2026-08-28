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

**Quick Look thumbnails are square.** `qlmanage` writes a 2400x2400 (or
1920x1920) PNG with transparent letterboxing above and below a 16:9 design. For
anything with a fixed aspect ratio — slide images especially — crop after
rendering or the deck will letterbox:

```bash
qlmanage -t -s 1920 -o docs/media docs/media/<name>.svg
mv docs/media/<name>.svg.png docs/media/<name>.png
sips -c 1080 1920 docs/media/<name>.png    # centred crop to exact 16:9
```

## Two families of diagram, and why they are not the same file

A diagram that documents and a diagram that projects have opposite constraints,
and trying to serve both produces something that fails at each:

| | Reference diagram | Slide diagram |
|---|---|---|
| Read | Zoomed in, at leisure | Three seconds, across a room |
| Density | High — every component, every number | At most ~9 labelled elements |
| Minimum type | 10.5px | **24px** |
| When it does not fit | Reflow, add a leader line | **Cut content — never shrink type** |
| Example | `architecture.svg`, `governance.svg` | `slide-architecture.svg`, `pitch-arithmetic.svg` |

The slide versions live beside the reference versions with a `slide-` or
`pitch-` prefix. They must never contradict the reference diagram — same
palette, same shape grammar, same facts, less of them.

### What only looking catches

Two real examples from this suite, both invisible in the source and obvious in
the render: a focal figure written as `17–18` read as *"17 minus 18"* at 230px
because an en dash at that scale looks like a minus sign; and a giant numeral
followed by a word collided, because a 240px digit has almost no side bearing —
the letter-spacing that looks generous at 12px is nothing at 240px.

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
`<name>.png` (2400px render for submissions and slides).

| Diagram | Level | Shows | Read it if you are |
|---|---|---|---|
| [`architecture`](architecture.svg) | overview | The whole engine on one page: ingest chain, the seven stages, memory tiers, the harness, and the surfaces | Anyone — this is the front door |
| [`context`](context.svg) | 1 — context | The school world around the engine: who touches it, what it exchanges with the SIS, the ministry standard and Google Cloud | Non-technical: leadership, a judge, a school |
| [`containers`](containers.svg) | 2 — containers | Deployable units and the data each owns, every Firestore collection named, and the identity carried on each hop | An engineer deciding whether this is real |
| [`pipeline`](pipeline.svg) | 3 — stages | One job stage by stage: inputs, model, cost, checkpoint, and where each stage refuses | Anyone reviewing the engineering |
| [`fleet`](fleet.svg) | 3 — agents | The twelve components with model, stage, capability scope and the principal each acts as | Anyone auditing the "agent fleet" claim |
| [`governance`](governance.svg) | 3 — controls | The ten gates a grade must survive before reaching a student record, in the order they apply, with what each one stopped | Anyone asking "can I trust this?" |
| [`self-improvement`](self-improvement.svg) | 3 — cold loop | How prompts improve against human ground truth, and how the anti-gaming gate refuses an unproven change | Anyone assessing the learning claim |
| [`exam-lifecycle`](exam-lifecycle.svg) | flow | One exam from the front-office scanner to a terminal state, on a real clock, with the human entry point marked | Anyone who wants the story end to end |
| [`resilience`](resilience.svg) | flow | The failure modes that were actually executed, and how each recovers | Anyone who has run production systems |
| [`teacher-journey`](teacher-journey.svg) | people | The teacher's seven screens and what she never sees | Product, design, and school buyers |

Every number in these diagrams comes from a dated report in `docs/reports/`.
Where a control is not yet proven in production, the diagram says so on its face
rather than implying more than was measured.
