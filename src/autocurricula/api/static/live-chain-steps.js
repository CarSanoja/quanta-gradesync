import { classifyEvent, injectionDetected, verificationLabel, verificationOf } from "./live-kinds.js";

export function callText(count) {
  return `${count} llm call${count === 1 ? "" : "s"}`;
}

export function llmCalls(events) {
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

function anchorSeq(part) {
  const source = part.source || {};
  return source.seq || null;
}

export function armorStep(armor) {
  const attributes = (armor.source && armor.source.attributes) || {};
  const severity = String(attributes["armor.severity"] || "none");
  const calls = callText(armor.calls.length);
  const seq = anchorSeq(armor);
  if (!armor.end) {
    return { label: "Armor screen", detail: `screening · ${calls}`, tone: "warn", seq };
  }
  if (injectionDetected(attributes)) {
    return {
      label: "Armor screen",
      detail: `injection detected · ${severity} · ${calls}`,
      tone: severity === "high" ? "error" : "warn",
      seq,
    };
  }
  return { label: "Armor screen", detail: `clean · ${calls}`, tone: "ok", seq };
}

export function gradedStep(events, grading, armor, faith) {
  const attributes = (grading.source && grading.source.attributes) || {};
  const calls = llmCalls(events);
  const own = Math.max(calls.length - armor.calls.length - faith.calls.length, 0);
  const outcome = String(attributes["submission.outcome"] || "");
  const failed = outcome === "failed" || (grading.end && grading.end.status === "error");
  const parts = [grading.end ? outcome || "graded" : "running"];
  parts.push(callText(own), `${tokensOf(calls) || fallbackTokens(attributes)} tok`);
  return {
    label: "Graded",
    detail: parts.join(" · "),
    tone: !grading.end ? "warn" : failed ? "error" : "ok",
    seq: anchorSeq(grading),
  };
}

export function faithfulnessStep(faith) {
  const attributes = (faith.source && faith.source.attributes) || {};
  const status = verificationOf(attributes);
  const detail = faith.present
    ? `${verificationLabel(attributes)} · ${callText(faith.calls.length)}`
    : verificationLabel({});
  const tone = status === "verified" ? "ok" : status === "failed" ? "error" : "warn";
  return { label: "Faithfulness", detail, tone, seq: anchorSeq(faith) };
}

export function denialSteps(events) {
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
        seq: event.seq || null,
      };
    });
}
