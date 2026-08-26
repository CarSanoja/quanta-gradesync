import {
  classifyEvent,
  injectionDetected,
  transcriptionTokens,
  verificationDetail,
  verificationLabel,
  verificationOf,
} from "./live-kinds.js";

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

export function gradedStep(events, grading, nested) {
  const attributes = (grading.source && grading.source.attributes) || {};
  const calls = llmCalls(events);
  const elsewhere = (nested || []).reduce((total, part) => total + part.calls.length, 0);
  const own = Math.max(calls.length - elsewhere, 0);
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

export function transcriptionStep(transcription) {
  const attributes = (transcription.source && transcription.source.attributes) || {};
  const tokens = transcriptionTokens(attributes);
  const running = !transcription.end;
  const failed = Boolean(transcription.end && transcription.end.status === "error");
  const parts = [running ? "reading the page" : "page text captured", tokens];
  return {
    label: "Page transcription",
    detail: parts.filter(Boolean).join(" · "),
    tone: failed ? "error" : "neutral",
    seq: anchorSeq(transcription),
  };
}

export function faithfulnessStep(faith) {
  const attributes = (faith.source && faith.source.attributes) || {};
  const status = verificationOf(attributes);
  if (!faith.present) {
    return {
      label: "Evidence check: not run for this student",
      detail: "no verification span recorded",
      tone: "neutral",
      seq: null,
    };
  }
  const tone = status === "verified" ? "ok" : status === "failed" ? "error" : "neutral";
  const calls = faith.calls.length ? callText(faith.calls.length) : "";
  return {
    label: verificationLabel(attributes),
    detail: [verificationDetail(attributes), calls].filter(Boolean).join(" · ") || "no quotes cited",
    tone,
    seq: anchorSeq(faith),
  };
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
