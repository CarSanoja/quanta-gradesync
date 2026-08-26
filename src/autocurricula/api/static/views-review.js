import {
  clear,
  el,
  emptyState,
  formatDateTime,
  formatNumber,
  formatPercent,
  metaRow,
  metric,
  pill,
} from "./render.js";
import { criteriaTable, scoreCeiling } from "./views-criteria.js";

const DRAWN_SPANS = 3;

function navigate(name, argument) {
  const go = window[name];
  if (typeof go === "function") {
    go(argument);
  }
}

export function renderReviewList(target, items, activeId, onSelect) {
  clear(target);
  if (!items.length) {
    target.append(emptyState("Queue is clear", "Every graded record cleared the confidence gate."));
    return;
  }
  const list = el("div", { class: "list" });
  items.forEach((item) => {
    list.append(
      el(
        "button",
        {
          type: "button",
          class: `list-item${item.review_id === activeId ? " is-active" : ""}`,
          onclick: () => onSelect(item.review_id),
        },
        [
          el("span", { class: "list-title" }, [
            el("span", { text: item.student_id }),
            pill(
              `${item.reasons.length} reason${item.reasons.length === 1 ? "" : "s"}`,
              "quarantined"
            ),
          ]),
          metaRow([
            item.subject,
            el("span", { class: "mono", text: item.job_id }),
            `queued ${formatDateTime(item.created_at)}`,
          ]),
        ]
      )
    );
  });
  target.append(list);
}

export function renderQueueCleared(target, lastJobId) {
  clear(target).append(emptyState("Queue is clear", "Nothing is waiting for a teacher decision."));
  if (!lastJobId) {
    return;
  }
  const button = el("button", {
    class: "ghost",
    type: "button",
    text: "See it in the SIS ledger",
    onclick: () => navigate("goToSisLedger", lastJobId),
  });
  target.append(el("div", { class: "actions is-inline" }, button));
}

function evidenceFrame(item, imageUrl) {
  const frame = el("div", { class: "evidence-frame" });
  if (imageUrl) {
    frame.append(el("img", { src: imageUrl, alt: `Scanned page for ${item.student_id}` }));
  } else {
    frame.append(
      emptyState("Scanned page unavailable", "The staged file could not be read in this mode.")
    );
  }
  if (item.evidence.length) {
    frame.append(
      el(
        "div",
        { class: "evidence-overlay" },
        item.evidence.slice(0, DRAWN_SPANS).map((span) =>
          el("div", { class: "callout" }, [
            el("div", { class: "callout-head" }, [
              el("span", { text: `page ${span.page}` }),
              el("span", { text: "cited evidence" }),
            ]),
            el("div", { class: "callout-quote", text: `“${span.quote}”` }),
            el("div", { class: "callout-why", text: span.rationale }),
          ])
        )
      )
    );
  }
  return frame;
}

function proposedScore(record, criteria) {
  const ceiling = scoreCeiling(criteria);
  if (ceiling === null) {
    return formatNumber(record.score, 1);
  }
  return `${formatNumber(record.score, 1)} / ${formatNumber(ceiling, 1)}`;
}

function reviewHead(item, record, criteria) {
  return [
    el("span", { class: "list-title" }, [
      el("span", { text: `${item.student_id} · ${item.subject}` }),
      pill(item.status, item.status),
    ]),
    metaRow([
      el("span", { class: "mono", text: item.job_id }),
      `graded ${formatDateTime(record.graded_at)}`,
      record.provenance ? `prompt ${record.provenance.prompt_variant_id}` : "prompt unversioned",
    ]),
    el("p", { class: "section-title", text: "Why it was quarantined" }),
    el(
      "ul",
      { class: "reasons" },
      item.reasons.map((reason) => el("li", { class: "reason", text: reason }))
    ),
    el("dl", { class: "metrics" }, [
      metric("Proposed score", proposedScore(record, criteria)),
      metric("Percentage", formatPercent(record.percentage)),
      metric("Competencies", String(record.competency_codes.length)),
      metric("Evidence spans", String(item.evidence.length)),
    ]),
  ];
}

export function renderReviewDetail(target, context, handlers) {
  clear(target);
  const item = context.item;
  if (!item) {
    target.append(
      emptyState("Select a quarantined item", "Reasons, evidence and the scan appear here.")
    );
    return;
  }
  const record = item.proposed_record;
  reviewHead(item, record, context.criteria).forEach((node) => target.append(node));
  target.append(
    el("p", { class: "section-title", text: "Proposed record, criterion by criterion" })
  );
  target.append(
    context.criteria.length
      ? criteriaTable(context.criteria)
      : emptyState(
          "Criterion detail unavailable",
          "The job checkpoint no longer holds the grading result."
        )
  );
  target.append(el("p", { class: "section-title", text: "Teacher feedback" }));
  target.append(el("p", { text: record.feedback }));
  target.append(el("p", { class: "section-title", text: "Scanned page with cited evidence" }));
  target.append(evidenceFrame(item, context.imageUrl));
  if (item.evidence.length > DRAWN_SPANS) {
    target.append(
      el("p", {
        class: "list-sub",
        text: `+${item.evidence.length - DRAWN_SPANS} more cited spans not drawn on the page`,
      })
    );
  }
  if (item.rework_notes.length) {
    target.append(el("p", { class: "section-title", text: "Rework notes" }));
    target.append(
      el(
        "ul",
        { class: "reasons" },
        item.rework_notes.map((note) => el("li", { class: "reason", text: note }))
      )
    );
  }
  target.append(
    el("div", { class: "actions" }, [
      el("button", {
        class: "primary",
        type: "button",
        text: "Approve and write to SIS",
        onclick: () => handlers.onApprove(item.review_id),
      }),
      el("button", {
        class: "ghost",
        type: "button",
        text: "Dismiss",
        onclick: () => handlers.onDismiss(item.review_id),
      }),
    ])
  );
}
