import { clear, el, emptyState, pill } from "./render.js";
import { classifyEvent, injectionDetected, verificationOf } from "./live-kinds.js";
import { groupByStudent } from "./live-chain-groups.js";

const CONFIDENCE_KEYS = ["grading.confidence", "submission.confidence", "confidence"];
const OPEN_SEQ = Number.MAX_SAFE_INTEGER;

function callText(count) {
  return `${count} llm call${count === 1 ? "" : "s"}`;
}

function llmCalls(events) {
  return events.filter((event) => event.kind === "llm_call");
}

function tokensOf(calls) {
  return calls.reduce((total, event) => {
    const llm = event.llm || {};
    const parts = (Number(llm.input_tokens) || 0) + (Number(llm.output_tokens) || 0);
    return total + (Number(llm.total_tokens) || parts);
  }, 0);
}

function fallbackTokens(attributes) {
  const inbound = Number(attributes["gen_ai.usage.input_tokens"]) || 0;
  const outbound = Number(attributes["gen_ai.usage.output_tokens"]) || 0;
  return inbound + outbound;
}

function confidenceOf(attributes) {
  for (const key of CONFIDENCE_KEYS) {
    const value = attributes[key];
    if (typeof value === "number") {
      return value;
    }
    if (typeof value === "string" && value !== "" && !Number.isNaN(Number(value))) {
      return Number(value);
    }
  }
  return null;
}

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

function armorStep(armor) {
  const attributes = (armor.source && armor.source.attributes) || {};
  const severity = String(attributes["armor.severity"] || "none");
  const calls = callText(armor.calls.length);
  if (!armor.end) {
    return { label: "Armor screen", detail: `screening · ${calls}`, tone: "warn" };
  }
  if (injectionDetected(attributes)) {
    return {
      label: "Armor screen",
      detail: `injection detected · ${severity} · ${calls}`,
      tone: severity === "high" ? "error" : "warn",
    };
  }
  return { label: "Armor screen", detail: `clean · ${calls}`, tone: "ok" };
}

function gradedStep(events, grading, armor, faith) {
  const attributes = (grading.source && grading.source.attributes) || {};
  const calls = llmCalls(events);
  const own = Math.max(calls.length - armor.calls.length - faith.calls.length, 0);
  const outcome = String(attributes["submission.outcome"] || "");
  const failed = outcome === "failed" || (grading.end && grading.end.status === "error");
  const parts = [grading.end ? outcome || "graded" : "running"];
  const confidence = confidenceOf(attributes);
  if (confidence !== null) {
    parts.push(`confidence ${confidence.toFixed(2)}`);
  }
  parts.push(callText(own), `${tokensOf(calls) || fallbackTokens(attributes)} tok`);
  return {
    label: "Graded",
    detail: parts.join(" · "),
    tone: !grading.end ? "warn" : failed ? "error" : "ok",
  };
}

function faithfulnessStep(faith) {
  const attributes = (faith.source && faith.source.attributes) || {};
  const status = faith.present ? verificationOf(attributes) : "unchecked";
  const detail = faith.present ? `${status} · ${callText(faith.calls.length)}` : "unchecked";
  const tone = status === "verified" ? "ok" : status === "failed" ? "error" : "warn";
  return { label: "Faithfulness", detail, tone };
}

function denialSteps(events) {
  return events
    .filter((event) => classifyEvent(event) === "permission" && event.kind !== "span_start")
    .map((event) => {
      const attributes = event.attributes || {};
      const capability =
        attributes["agent.capability"] || attributes["permission.target"] || "capability";
      const reason = String(attributes["permission.reason"] || "");
      return {
        label: "Permission denied",
        detail: [capability, reason].filter(Boolean).join(" · "),
        tone: "error",
      };
    });
}

function stepNode(step) {
  return el("div", { class: `chain-step is-${step.tone}` }, [
    el("span", { class: "mono", text: step.label }),
    el("span", { class: "list-sub", text: step.detail }),
  ]);
}

function chainCard(student, events) {
  const armor = segment(events, "armor");
  const grading = segment(events, "grading");
  const faith = segment(events, "faithfulness");
  const steps = armor.present ? [armorStep(armor)] : [];
  steps.push(gradedStep(events, grading, armor, faith), faithfulnessStep(faith));
  denialSteps(events).forEach((step) => steps.push(step));
  const failed = steps.some((step) => step.tone === "error");
  const running = !grading.end;
  const state = failed ? "failed" : running ? "running" : "succeeded";
  const label = failed ? "attention" : running ? "in flight" : "settled";
  return el("div", { class: "chain-card" }, [
    el("div", { class: "chain-student" }, [
      el("span", { class: "mono", text: student }),
      pill(label, state),
    ]),
    el("div", { class: "chain-steps" }, steps.map(stepNode)),
    running
      ? el("div", {
          class: "chain-note",
          text: `Still in flight · ${events.length} events so far`,
        })
      : null,
  ]);
}

export function renderChains(target, events, meta) {
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
  const chain = el("div", { class: "chain" });
  groups.forEach((studentEvents, student) => {
    chain.append(chainCard(student, studentEvents));
  });
  target.append(chain);
}
