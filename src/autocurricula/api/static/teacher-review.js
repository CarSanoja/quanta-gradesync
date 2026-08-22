import { endpoints, getObjectUrl } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";
import { firstName, fmt, pointsOf } from "/teacher/assets/teacher-format.js";

export const STEP = 0.5;

export function markValue(ctx, criterion) {
  if (!ctx.editing || !ctx.marks) {
    return criterion.score;
  }
  const held = ctx.marks[criterion.criterion_id];
  return held === undefined ? criterion.score : held;
}

export function bumped(current, delta, ceiling) {
  const raw = Math.round((current + delta) * 100) / 100;
  const top = ceiling === null || ceiling === undefined ? raw : Math.min(raw, ceiling);
  return Math.max(0, top);
}

function markRow(ctx, criterion) {
  const value = markValue(ctx, criterion);
  const max = criterion.max_score;
  const controls = [];
  if (ctx.editing) {
    controls.push(el("button", {
      class: "stepper",
      type: "button",
      id: `step-down-${criterion.criterion_id}`,
      "aria-label": `One step fewer on ${criterion.title}`,
      disabled: value <= 0,
      text: "−",
      onclick: () => ctx.onBump(criterion, -STEP),
    }));
  }
  controls.push(el("span", { class: "mark-score", text: pointsOf(value, max) }));
  if (ctx.editing) {
    controls.push(el("button", {
      class: "stepper",
      type: "button",
      id: `step-up-${criterion.criterion_id}`,
      "aria-label": `One step more on ${criterion.title}`,
      disabled: max !== null && max !== undefined && value >= max,
      text: "+",
      onclick: () => ctx.onBump(criterion, STEP),
    }));
  }
  return el("li", {}, [
    el("div", { class: "mark-row" }, [
      el("span", { class: "mark-title", text: criterion.title }),
      el("span", { class: "mark-controls" }, controls),
    ]),
    criterion.comment && !ctx.editing
      ? el("p", { class: "mark-note", text: criterion.comment })
      : null,
  ]);
}

export function totalLine(ctx) {
  const review = ctx.review;
  const scored = review.criteria.reduce((sum, criterion) => sum + markValue(ctx, criterion), 0);
  const total = review.criteria.length ? scored : review.score;
  const ceiling = review.max_score;
  if (ceiling === null || ceiling === undefined || ceiling <= 0) {
    return `Total: ${fmt(total)} points`;
  }
  return `Total: ${fmt(total)} of ${fmt(ceiling)} points · ${Math.round((total / ceiling) * 100)}%`;
}

function points(list) {
  return el("ul", { class: "band-list" }, list.map((point) => el("li", {}, [
    el("span", { text: point.text }),
    point.quote
      ? el("span", { class: "band-cite", text: `“${point.quote}”${point.page ? ` — page ${point.page}` : ""}` })
      : null,
  ])));
}

function studentFeedback(review) {
  const written = review.student_feedback;
  const banded = written
    && (written.headline || written.next_step || (written.strengths || []).length || (written.growth || []).length);
  if (!banded) {
    return [el("p", { class: "band-step", text: review.feedback })];
  }
  const nodes = [];
  if (written.headline) {
    nodes.push(el("p", { class: "feedback-headline", text: written.headline }));
  }
  if ((written.strengths || []).length) {
    nodes.push(el("p", { class: "band-tag", text: "What went well" }), points(written.strengths));
  }
  if ((written.growth || []).length) {
    nodes.push(el("p", { class: "band-tag", text: "What to improve" }), points(written.growth));
  }
  if (written.next_step) {
    nodes.push(el("p", { class: "band-tag", text: "Next step" }),
      el("p", { class: "band-step", text: written.next_step }));
  }
  return nodes;
}

function reasonCard(review) {
  const rest = review.reasons.filter((reason) => reason !== review.primary_reason);
  return el("div", { class: "reason-card" }, [
    el("p", { class: "reason-tag", text: "Why this one stopped" }),
    el("p", { class: "reason-main", text: review.primary_reason }),
    rest.length
      ? el("ul", { class: "reason-extra" }, rest.map((reason) => el("li", { text: reason })))
      : null,
  ]);
}

function quoteBlock(review) {
  const span = review.evidence[0];
  if (!span) {
    return [];
  }
  const where = span.note ? `page ${span.page} · ${span.note}` : `page ${span.page}`;
  return [
    el("p", { class: "quote-intro", text: "The grader read this from the page:" }),
    el("blockquote", { class: "quote" }, [el("span", { text: span.quote })]),
    el("p", { class: "quote-where", text: where }),
  ];
}

function decisions(ctx) {
  const review = ctx.review;
  const approve = el("button", { class: "primary", type: "button" }, [
    ctx.editing ? "Save these marks to the gradebook" : "Put it in the gradebook",
    el("kbd", { text: "A" }),
  ]);
  approve.addEventListener("click", () => ctx.onAccept(approve));
  const nodes = [approve];
  if (review.can_edit_marks) {
    nodes.push(el("button", {
      class: "secondary",
      type: "button",
      text: ctx.editing ? "Leave the marks as they were" : "Change the marks",
      onclick: () => ctx.onToggleEdit(),
    }));
  }
  const mine = el("button", { class: "grade-myself", type: "button" }, [
    "I'll grade this one myself", el("kbd", { text: "S" }),
  ]);
  mine.addEventListener("click", () => ctx.onDismiss(mine));
  nodes.push(mine);
  return el("div", { class: "decisions" }, nodes);
}

function sidePanel(ctx) {
  const review = ctx.review;
  const marks = review.criteria.length
    ? el("ul", { class: "marks" }, review.criteria.map((criterion) => markRow(ctx, criterion)))
    : el("p", { class: "marks-empty", text: "The mark-by-mark breakdown is not stored for this exam, so it cannot be changed here." });
  const note = review.student_feedback && review.student_feedback.teacher_note;
  const first = firstName(review.student_name);
  return el("div", { class: "review-side" }, [
    reasonCard(review),
    ...quoteBlock(review),
    el("h3", { class: "marks-title", text: "The marks we propose" }),
    marks,
    el("p", { class: "marks-total", text: totalLine(ctx) }),
    el("details", { class: "disclosure", id: "disclosure-student", open: ctx.open.student }, [
      el("summary", { text: `What ${first} will see` }),
      el("div", { class: "disclosure-body" }, studentFeedback(review)),
    ]),
    note
      ? el("details", { class: "disclosure is-last", id: "disclosure-teacher", open: ctx.open.teacher }, [
          el("summary", { text: "A note only for you" }),
          el("div", { class: "disclosure-body" }, [
            el("p", { class: "band-step", text: note }),
            el("p", { class: "teacher-only", text: `${first} never sees this note.` }),
          ]),
        ])
      : el("div", { class: "disclosure is-last" }),
    decisions(ctx),
  ]);
}

export function decisionButtons(host) {
  return [...host.querySelectorAll(".decisions .primary, .decisions .grade-myself")];
}

export async function renderReview(host, ctx) {
  const review = ctx.review;
  clear(host);
  host.className = "screen is-review";
  const frame = el("div", { class: "scan-frame" }, [
    el("span", { class: "scan-placeholder", text: "Loading the scanned page…" }),
  ]);
  const zoom = el("button", {
    class: "secondary",
    type: "button",
    id: "scan-zoom",
    text: "See it bigger",
    disabled: true,
    onclick: () => ctx.onZoom(),
  });
  host.append(
    el("div", { class: "review-head" }, [
      el("div", { class: "brand" }, [
        el("span", { class: "review-position", text: `Exam ${ctx.position} of ${ctx.total} waiting` }),
        el("span", { class: "review-student", text: review.student_name }),
      ]),
      el("button", {
        class: "linkish",
        type: "button",
        text: "Stop for now — the rest keep waiting",
        onclick: () => ctx.onLeave(),
      }),
    ]),
    el("div", { class: "review-grid" }, [
      el("div", { class: "review-scan" }, [frame, el("div", { class: "scan-tools" }, [zoom])]),
      sidePanel(ctx),
    ])
  );
  if (!review.has_page) {
    clear(frame).append(el("span", { class: "scan-placeholder", text: "No scan is attached to this exam." }));
    return null;
  }
  try {
    const url = await getObjectUrl(endpoints.pageImage(review.review_id, 0));
    if (!ctx.stillOpen(review.review_id)) {
      URL.revokeObjectURL(url);
      return null;
    }
    clear(frame).append(el("img", { src: url, alt: `Scanned exam page from ${review.student_name}` }));
    zoom.disabled = false;
    return url;
  } catch (error) {
    clear(frame).append(el("span", { class: "scan-placeholder", text: "The scan could not be loaded right now." }));
    return null;
  }
}
