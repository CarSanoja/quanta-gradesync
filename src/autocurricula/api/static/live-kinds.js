export const KIND_LABELS = {
  llm: "llm",
  armor: "armor",
  permission: "permission",
  stage: "stage",
  grading: "grading",
  faithfulness: "evidence",
  span: "span",
};

export function classifyEvent(event) {
  if (event.kind === "llm_call") {
    return "llm";
  }
  const name = event.name || "";
  if (name === "ArmorScreen") {
    return "armor";
  }
  if (name === "CapabilityDenied") {
    return "permission";
  }
  if (name === "FaithfulnessVerification") {
    return "faithfulness";
  }
  if (name.startsWith("Stage_")) {
    return "stage";
  }
  if (name.startsWith("Grading_")) {
    return "grading";
  }
  return "span";
}

export function isTickerEvent(event) {
  if (event.kind !== "span_start") {
    return true;
  }
  const kind = classifyEvent(event);
  return kind === "stage" || kind === "grading";
}

export function injectionDetected(attributes) {
  return (attributes || {})["armor.injection_detected"] === true;
}

export function verificationOf(attributes) {
  return String((attributes || {})["evidence.span_verification"] || "unchecked");
}

const VERIFICATION_LABELS = {
  verified: "evidence verified",
  failed: "evidence check failed",
};

export function verificationLabel(attributes) {
  return VERIFICATION_LABELS[verificationOf(attributes)] || "evidence not verified yet";
}

export function clockTime(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value || "—");
  }
  return parsed.toLocaleTimeString(undefined, {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function durationText(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

export function tokenText(input, output) {
  const inbound = Number(input) || 0;
  const outbound = Number(output) || 0;
  if (!inbound && !outbound) {
    return "";
  }
  return `${inbound} in / ${outbound} out tok`;
}

export function toneOf(event, kind) {
  const attributes = event.attributes || {};
  if (event.status === "error") {
    return "failed";
  }
  if (kind === "armor") {
    return injectionDetected(attributes) ? "failed" : "succeeded";
  }
  if (kind === "permission") {
    return "failed";
  }
  if (kind === "grading") {
    if (event.kind === "span_start") {
      return "running";
    }
    return attributes["submission.outcome"] === "failed" ? "failed" : "succeeded";
  }
  if (kind === "faithfulness") {
    const verification = verificationOf(attributes);
    if (verification === "failed") {
      return "failed";
    }
    return verification === "verified" ? "succeeded" : "pending";
  }
  if (kind === "llm" || event.kind === "span_start") {
    return "running";
  }
  return "succeeded";
}

export function isFailure(event, kind) {
  const attributes = event.attributes || {};
  if (event.status === "error" || kind === "permission") {
    return true;
  }
  if (kind === "armor") {
    return injectionDetected(attributes);
  }
  return kind === "faithfulness" && verificationOf(attributes) === "failed";
}
