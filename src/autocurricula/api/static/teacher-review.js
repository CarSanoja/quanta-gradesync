import { endpoints, getObjectUrl } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";
import { firstName, fmt, prettySubject } from "/teacher/assets/teacher-format.js";
import { bumped, confidenceBand, markValue, marksBlock } from "/teacher/assets/teacher-marks.js";

const IMAGE_CACHE_LIMIT = 12;
const imageCache = new Map();
const imageLoads = new Map();

export { bumped, markValue };

async function reviewImage(reviewId) {
  if (imageCache.has(reviewId)) {
    const url = imageCache.get(reviewId);
    imageCache.delete(reviewId);
    imageCache.set(reviewId, url);
    return url;
  }
  if (!imageLoads.has(reviewId)) {
    const pending = getObjectUrl(endpoints.pageImage(reviewId, 0)).then((url) => {
      imageCache.set(reviewId, url);
      while (imageCache.size > IMAGE_CACHE_LIMIT) {
        const oldest = imageCache.keys().next().value;
        URL.revokeObjectURL(imageCache.get(oldest));
        imageCache.delete(oldest);
      }
      return url;
    }).finally(() => imageLoads.delete(reviewId));
    imageLoads.set(reviewId, pending);
  }
  return imageLoads.get(reviewId);
}

export function releaseReviewImages() {
  imageCache.forEach((url) => URL.revokeObjectURL(url));
  imageCache.clear();
  imageLoads.clear();
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

function figures(ctx) {
  const review = ctx.review;
  const scored = review.criteria.reduce((sum, criterion) => sum + markValue(ctx, criterion), 0);
  const total = review.criteria.length ? scored : review.score;
  const ceiling = review.max_score;
  const pct = ceiling ? Math.round((total / ceiling) * 100) : Math.round(review.percentage);
  const sure = confidenceBand(review.confidence_band);
  return el("div", { class: "review-figures" }, [
    el("div", {}, [
      el("p", { class: "figure-n", text: fmt(total) }),
      el("p", { class: "figure-label", text: ceiling ? `points of ${fmt(ceiling)}` : "points" }),
    ]),
    el("div", {}, [
      el("p", { class: "figure-n is-accent", text: `${pct}%` }),
      el("p", { class: "figure-label", text: "of the rubric" }),
    ]),
    el("div", { class: "confidence" }, [
      el("p", { class: "figure-label", text: `the grader was ${sure.word}` }),
      el("div", { class: "confidence-track" }, [
        el("span", { class: `confidence-fill${sure.tone}`, style: `width:${sure.share}%` }),
      ]),
    ]),
  ]);
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
    el("p", { class: "quote-intro", text: "The grader read this from the page" }),
    el("blockquote", { class: "quote" }, [el("span", { text: span.quote })]),
    el("p", { class: "quote-where", text: where }),
  ];
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

function decisions(ctx) {
  const review = ctx.review;
  if (ctx.readonly) {
    return el("div", { class: "decisions" }, [
      el("p", {
        class: "mark-note",
        text: "This decision is already recorded. You can inspect it, then move to another exam.",
      }),
    ]);
  }
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
  if (ctx.restHeld > 0) {
    nodes.push(el("button", {
      class: "apply-rest",
      type: "button",
      text: `Put the other ${ctx.restHeld} held ${ctx.restHeld === 1 ? "exam" : "exams"} in too`,
      onclick: () => ctx.onApplyRest(),
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
  const note = review.student_feedback && review.student_feedback.teacher_note;
  const first = firstName(review.student_name);
  const meta = [prettySubject(review.subject), review.class_id ? `class ${review.class_id}` : "",
    review.assessment].filter(Boolean).join(" · ");
  return el("div", { class: "review-side" }, [
    el("h1", { class: "review-student", text: review.student_name }),
    el("p", { class: "review-meta", text: meta }),
    figures(ctx),
    reasonCard(review),
    ...quoteBlock(review),
    el("h2", { class: "marks-title", text: "The marks we propose" }),
    el("p", {
      class: "marks-lede",
      text: "The rubric's own wording, the points, and the line the grader read for each one.",
    }),
    marksBlock(ctx),
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
    el("span", { class: "scan-placeholder is-loading", text: "Loading the scanned page…" }),
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
      el("div", { class: "review-crumbs" }, [
        el("button", { class: "quiet", type: "button", text: "← The batch", onclick: () => ctx.onLeave() }),
        el("span", { class: "review-position", text: `Exam ${ctx.position} of ${ctx.total} waiting` }),
      ]),
      el("div", { class: "review-navigation" }, [
        el("button", {
          class: "quiet",
          type: "button",
          text: "← Previous",
          disabled: ctx.position <= 1,
          onclick: () => ctx.onPrevious(),
        }),
        el("button", {
          class: "quiet",
          type: "button",
          text: "Next →",
          disabled: ctx.position >= ctx.total,
          onclick: () => ctx.onNext(),
        }),
      ]),
    ]),
    el("div", { class: "review-grid" }, [
      el("div", { class: "review-scan" }, [
        frame,
        el("div", { class: "scan-tools" }, [
          zoom,
          el("span", { class: "review-position", text: `scan · ${review.student_name}` }),
        ]),
      ]),
      sidePanel(ctx),
    ])
  );
  if (!review.has_page) {
    clear(frame).append(el("span", { class: "scan-placeholder", text: "No scan is attached to this exam." }));
    return null;
  }
  try {
    const url = await reviewImage(review.review_id);
    if (!ctx.stillOpen(review.review_id)) {
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
