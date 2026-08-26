import { clear, el, emptyState, formatPercent, pill } from "./render.js";
import { classifyEvent } from "./live-kinds.js";
import { groupByStudent } from "./live-chain-groups.js";
import {
  armorStep,
  denialSteps,
  faithfulnessStep,
  gradedStep,
  llmCalls,
} from "./live-chain-steps.js";

const OPEN_SEQ = Number.MAX_SAFE_INTEGER;

function segment(events, kind) {
  const matching = events.filter((event) => classifyEvent(event) === kind);
  const start = matching.find((event) => event.kind === "span_start") || null;
  const end = matching.find((event) => event.kind === "span_end") || null;
  const anchor = start || end;
  const from = anchor ? anchor.seq : null;
  const until = end ? end.seq : OPEN_SEQ;
  const calls =
    from === null
      ? []
      : llmCalls(events).filter((event) => event.seq >= from && event.seq <= until);
  return { start, end, calls, present: Boolean(anchor), source: end || start };
}

function stepNode(step, onSelect) {
  return el(
    "button",
    {
      type: "button",
      class: `chain-step is-${step.tone}`,
      disabled: !step.seq,
      onclick: () => {
        if (onSelect && step.seq) {
          onSelect(step.seq);
        }
      },
    },
    [
      el("span", { class: "mono", text: step.label }),
      el("span", { class: "list-sub", text: step.detail }),
    ]
  );
}

function outcomeNodes(summary) {
  if (!summary) {
    return [];
  }
  return [
    summary.percentage === null ? null : el("span", { text: formatPercent(summary.percentage) }),
    summary.lowestConfidence === null
      ? null
      : el("span", { text: `confidence ${summary.lowestConfidence.toFixed(2)}` }),
    summary.sisStatus ? pill(summary.sisStatus, summary.sisStatus) : null,
  ].filter(Boolean);
}

function chainCard(student, events, summary, onSelect) {
  const armor = segment(events, "armor");
  const grading = segment(events, "grading");
  const faith = segment(events, "faithfulness");
  const steps = armor.present ? [armorStep(armor)] : [];
  steps.push(gradedStep(events, grading, armor, faith), faithfulnessStep(faith));
  denialSteps(events).forEach((step) => steps.push(step));
  const failed = steps.some((step) => step.tone === "error");
  const warned = steps.some((step) => step.tone === "warn");
  const running = !grading.end;
  const settledState = warned ? "quarantined" : "succeeded";
  const settledLabel = warned ? "settled with warnings" : "settled";
  const state = failed ? "failed" : running ? "running" : settledState;
  const label = failed ? "attention" : running ? "in flight" : settledLabel;
  return el("div", { class: "chain-card" }, [
    el("div", { class: "chain-student" }, [
      el("span", { class: "mono", text: student }),
      el("div", { class: "chain-outcome" }, outcomeNodes(summary).concat(pill(label, state))),
    ]),
    el(
      "div",
      { class: "chain-steps" },
      steps.map((step) => stepNode(step, onSelect))
    ),
    running
      ? el("div", {
          class: "chain-note",
          text: `Still in flight · ${events.length} events so far`,
        })
      : null,
  ]);
}

export function renderChains(target, events, meta, onSelect) {
  clear(target);
  const groups = groupByStudent(events);
  if (!groups.size) {
    const jobId = meta && meta.jobId;
    target.append(
      emptyState(
        "No student chains yet",
        jobId
          ? `Job ${jobId} has not reached the grading stage yet.`
          : "Each student gets a chain once grading starts."
      )
    );
    return;
  }
  const summaries = meta && meta.students instanceof Map ? meta.students : new Map();
  const chain = el("div", { class: "chain" });
  groups.forEach((studentEvents, student) => {
    chain.append(chainCard(student, studentEvents, summaries.get(student) || null, onSelect));
  });
  target.append(chain);
}
