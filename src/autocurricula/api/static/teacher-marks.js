import { el } from "/console/assets/render.js";
import { pointsOf } from "/teacher/assets/teacher-format.js";

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

const BANDS = {
  high: { word: "sure of this reading", tone: " is-high", share: 100 },
  middling: { word: "fairly sure of this reading", tone: "", share: 62 },
  low: { word: "not sure of this reading", tone: " is-low", share: 28 },
};

export function confidenceBand(band) {
  return BANDS[band] || { word: "not recorded", tone: "", share: 0 };
}

function evidenceBlock(criterion) {
  const span = (criterion.evidence || [])[0];
  if (!span) {
    return null;
  }
  const where = span.note ? `page ${span.page} · ${span.note}` : `page ${span.page}`;
  return el("div", { class: "mark-evidence" }, [
    el("p", { class: "mark-evidence-where", text: `what the student wrote · ${where}` }),
    el("p", { class: "mark-evidence-quote" }, [el("span", { text: span.quote })]),
  ]);
}

function steppers(ctx, criterion, value) {
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
  return el("span", { class: "mark-controls" }, controls);
}

function markRow(ctx, criterion) {
  const value = markValue(ctx, criterion);
  const confidence = criterion.confidence_band;
  return el("li", {}, [
    el("div", { class: "mark-row" }, [
      el("span", { class: "mark-title", text: criterion.title }),
      steppers(ctx, criterion, value),
    ]),
    evidenceBlock(criterion),
    confidence
      ? el("p", {
          class: "mark-confidence",
          text: `the grader was ${confidenceBand(confidence).word}`,
        })
      : null,
    criterion.comment && !ctx.editing
      ? el("p", { class: "mark-note", text: criterion.comment })
      : null,
  ]);
}

export function marksBlock(ctx) {
  const review = ctx.review;
  if (!review.criteria.length) {
    return el("p", {
      class: "marks-empty",
      text: "The mark-by-mark breakdown is not stored for this exam, so it cannot be changed here.",
    });
  }
  return el("ul", { class: "marks" }, review.criteria.map((criterion) => markRow(ctx, criterion)));
}
