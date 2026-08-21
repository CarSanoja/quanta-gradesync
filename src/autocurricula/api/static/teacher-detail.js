import { endpoints, getObjectUrl } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";

const GROUP_LABELS = {
  judgement: "Needs your judgement",
  batch_hold: "Held only by the batch rule",
};

export function prettySubject(subject) {
  const plain = String(subject).replace(/[-_]+/g, " ");
  return plain ? plain[0].toUpperCase() + plain.slice(1) : subject;
}

export function timeAgo(value) {
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) {
    return "";
  }
  const minutes = Math.round((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return hours === 1 ? "an hour ago" : `${hours} hours ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function scanSide(review) {
  const frame = el("div", { class: "scan-frame" }, [
    el("div", { class: "scan-missing", text: "Loading the scanned page…" }),
  ]);
  const flags = el("ul", { class: "evidence-stack" }, review.evidence.map((span) =>
    el("li", { class: "evidence-flag" }, [
      el("span", { class: "page-tab", text: `Page ${span.page}` }),
      el("q", { text: span.quote }),
      el("span", { class: "note", text: span.note }),
    ])
  ));
  const side = el("div", { class: "scan-side" }, [
    frame,
    review.evidence.length ? flags : null,
    el("p", {
      class: "scan-caption",
      text: "The scanned page, exactly as it was uploaded. Quotes below are the grader's evidence.",
    }),
  ]);
  return { side, frame };
}

function feedbackPoints(points) {
  return el("ul", { class: "feedback-points" }, points.map((point) =>
    el("li", {}, [
      el("span", { class: "point-text", text: point.text }),
      point.quote
        ? el("q", { class: "point-quote", text: point.quote })
        : null,
      point.quote && point.page
        ? el("span", { class: "point-page", text: `page ${point.page}` })
        : null,
    ])
  ));
}

function studentFeedback(review) {
  const written = review.student_feedback;
  if (!written) {
    return [
      el("h3", { text: "Feedback for the student" }),
      el("p", { class: "feedback", text: review.feedback }),
    ];
  }
  const nodes = [el("h3", { text: "Feedback for the student" })];
  const card = el("div", { class: "student-feedback" }, [
    written.headline ? el("p", { class: "feedback-headline", text: written.headline }) : null,
    written.strengths && written.strengths.length
      ? el("div", { class: "feedback-block" }, [
          el("h4", { text: "What worked" }),
          feedbackPoints(written.strengths),
        ])
      : null,
    written.growth && written.growth.length
      ? el("div", { class: "feedback-block" }, [
          el("h4", { text: "Next attempt" }),
          feedbackPoints(written.growth),
        ])
      : null,
    written.next_step
      ? el("p", { class: "feedback-step" }, [
          el("span", { class: "step-tag", text: "Do next" }),
          el("span", { text: written.next_step }),
        ])
      : null,
  ]);
  nodes.push(card);
  if (!written.headline && !written.next_step
    && !(written.strengths || []).length && !(written.growth || []).length) {
    nodes.push(el("p", { class: "feedback", text: review.feedback }));
  }
  if (written.teacher_note) {
    nodes.push(el("div", { class: "teacher-note" }, [
      el("span", { class: "note-tag", text: "For you only — the student never sees this" }),
      el("p", { text: written.teacher_note }),
    ]));
  }
  return nodes;
}

function decisionSide(review, onDecide) {
  const grades = review.criteria.length
    ? el("ul", { class: "grade-lines" }, review.criteria.map((criterion) =>
        el("li", {}, [
          el("div", { class: "grade-line-top" }, [
            el("span", { class: "title", text: criterion.title }),
            el("span", { class: "points", text: criterion.score_text }),
          ]),
          el("p", { class: "comment", text: criterion.comment }),
        ])
      ))
    : el("p", { class: "feedback", text: "The grade breakdown isn't available for this exam." });
  const approve = el("button", { class: "primary", type: "button" }, [
    "Approve grade ", el("kbd", { text: "A" }),
  ]);
  const sendBack = el("button", { class: "send-back", type: "button" }, [
    "I'll grade it myself ", el("kbd", { text: "S" }),
  ]);
  approve.addEventListener("click", () => onDecide(review, "approve", [approve, sendBack]));
  sendBack.addEventListener("click", () => onDecide(review, "dismiss", [approve, sendBack]));
  return el("div", { class: "decision-side" }, [
    el("h3", { text: "Why it needs you" }),
    el("ul", { class: "reason-list" }, review.reasons.map((reason) => el("li", { text: reason }))),
    el("h3", { text: "The proposed grade" }),
    grades,
    el("div", { class: "grade-total" }, [
      el("span", { class: "points", text: review.score_text }),
      el("span", { class: "percent", text: `${Math.round(review.percentage)}%` }),
    ]),
    ...studentFeedback(review),
    el("div", { class: "decision-actions" }, [approve, sendBack]),
    el("p", {
      class: "decision-hint",
      text: "Approve puts this grade in the gradebook. The other way records no grade, so this exam comes back to you to grade by hand.",
    }),
  ]);
}

export function detailButtons(host) {
  return [...host.querySelectorAll(".decision-actions button")];
}

export async function renderDetail(review, host, options) {
  const { onDecide, isOpen, scroll } = options;
  clear(host);
  host.hidden = false;
  const { side, frame } = scanSide(review);
  host.append(
    el("div", { class: "detail-head" }, [
      el("h2", { text: review.student_name }),
      el("span", {
        class: "context",
        text: `${prettySubject(review.subject)} · waiting ${timeAgo(review.waiting_since)}`,
      }),
      el("span", { class: "group-tag", "data-group": review.group, text: GROUP_LABELS[review.group] || "" }),
    ]),
    el("div", { class: "detail-grid" }, [side, decisionSide(review, onDecide)])
  );
  if (scroll) {
    host.scrollIntoView({ behavior: scroll, block: "nearest" });
  }
  if (!review.has_page) {
    clear(frame).append(el("div", { class: "scan-missing", text: "No scan is attached to this exam." }));
    return null;
  }
  try {
    const url = await getObjectUrl(endpoints.pageImage(review.review_id, 0));
    if (!isOpen(review.review_id)) {
      URL.revokeObjectURL(url);
      return null;
    }
    clear(frame).append(el("img", {
      src: url,
      alt: `Scanned exam page from ${review.student_name}`,
    }));
    return url;
  } catch (error) {
    clear(frame).append(el("div", { class: "scan-missing", text: "The scan couldn't be loaded right now." }));
    return null;
  }
}
