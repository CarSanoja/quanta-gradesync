import { clear, el, emptyState, pill } from "./render.js";
import {
  KIND_LABELS,
  classifyEvent,
  clockTime,
  durationText,
  injectionDetected,
  isFailure,
  isTickerEvent,
  toneOf,
  tokenText,
  transcriptionTokens,
  verificationDetail,
  verificationLabel,
} from "./live-kinds.js";
import { filterLabel, matchesFocus } from "./live-focus.js";

export { renderEventDetail } from "./live-detail.js";

const DECISION_LABELS = {
  deny: "DENIED",
  quarantine: "QUARANTINED",
  allow: "ALLOWED",
};

function withError(meta, event, attributes) {
  const type = event.status === "error" ? attributes["error.type"] : "";
  return [meta, type].filter(Boolean).join(" · ");
}

function describe(event, kind) {
  const attributes = event.attributes || {};
  const llm = event.llm || null;
  if (kind === "llm") {
    const tokens = llm ? tokenText(llm.input_tokens, llm.output_tokens) : "";
    const parts = [event.agent_id, tokens, llm ? llm.finish_reason : ""];
    return { label: (llm && llm.model) || event.name, meta: parts.filter(Boolean).join(" · ") };
  }
  if (kind === "armor") {
    const severity = String(attributes["armor.severity"] || "none");
    return {
      label: injectionDetected(attributes) ? `INJECTION ${severity}` : "clean",
      meta: [event.student_id, event.agent_id].filter(Boolean).join(" · "),
    };
  }
  if (kind === "permission") {
    const decision = String(attributes["permission.decision"] || "deny");
    const capability = attributes["agent.capability"] || attributes["permission.target"] || "";
    return {
      label: `${DECISION_LABELS[decision] || decision.toUpperCase()} ${capability}`.trim(),
      meta: String(attributes["permission.reason"] || event.agent_id || ""),
    };
  }
  if (kind === "grading") {
    const tokens = tokenText(
      attributes["gen_ai.usage.input_tokens"],
      attributes["gen_ai.usage.output_tokens"]
    );
    const outcome = attributes["submission.outcome"];
    const settled = [outcome || event.status, tokens].filter(Boolean).join(" · ");
    return {
      label: event.student_id || event.name.replace("Grading_", ""),
      meta: withError(event.kind === "span_start" ? "grading started" : settled, event, attributes),
    };
  }
  if (kind === "stage") {
    return {
      label: event.stage || event.name.replace("Stage_", ""),
      meta: withError(
        event.kind === "span_start" ? "running" : String(event.status),
        event,
        attributes
      ),
    };
  }
  if (kind === "transcription") {
    const tokens = transcriptionTokens(attributes);
    const done = event.kind !== "span_start";
    const label = done ? "Page transcribed" : "Transcribing the page";
    return {
      label: [label, tokens].filter(Boolean).join(" · "),
      meta: [event.student_id, event.agent_id].filter(Boolean).join(" · "),
    };
  }
  if (kind === "faithfulness") {
    return {
      label: verificationLabel(attributes),
      meta: [event.student_id, verificationDetail(attributes)].filter(Boolean).join(" · "),
    };
  }
  return { label: event.name, meta: event.stage || String(event.status) };
}

function tickerRow(event, selectedSeq, onSelect) {
  const kind = classifyEvent(event);
  const described = describe(event, kind);
  const classes = ["ticker-row", `kind-${kind}`];
  if (event.seq === selectedSeq) {
    classes.push("is-selected");
  }
  if (isFailure(event, kind)) {
    classes.push("is-error");
  }
  const trailing = [described.meta, durationText(event.duration_ms)].filter(Boolean);
  return el(
    "button",
    {
      type: "button",
      class: classes.join(" "),
      onclick: () => {
        if (onSelect) {
          onSelect(event.seq);
        }
      },
    },
    [
      el("span", { class: "ticker-time mono", text: clockTime(event.recorded_at) }),
      pill(KIND_LABELS[kind], toneOf(event, kind)),
      el("span", { class: "ticker-label", text: described.label }),
      el(
        "span",
        { class: "ticker-meta" },
        trailing.map((part) => el("span", { text: part }))
      ),
    ]
  );
}

function filterRow(label, onClearFilter) {
  return el("div", { class: "ticker-filter" }, [
    el("span", { text: `showing ${label}` }),
    el("button", {
      type: "button",
      class: "ghost",
      text: "clear",
      onclick: () => {
        if (onClearFilter) {
          onClearFilter();
        }
      },
    }),
  ]);
}

function scrollAnchor(target) {
  const existing = target.querySelector(".ticker");
  if (!existing || existing.scrollTop <= 0) {
    return null;
  }
  return { top: existing.scrollTop, height: existing.scrollHeight };
}

function restoreScroll(ticker, anchor) {
  if (!anchor) {
    return;
  }
  const grown = Math.max(0, ticker.scrollHeight - anchor.height);
  ticker.scrollTop = anchor.top + grown;
}

export function renderTicker(target, events, selectedSeq, onSelect, options) {
  const settings = options || {};
  const anchor = scrollAnchor(target);
  clear(target);
  const label = filterLabel(settings);
  const rows = (events || [])
    .filter(isTickerEvent)
    .filter((event) => matchesFocus(event, settings))
    .slice()
    .sort((left, right) => right.seq - left.seq);
  const ticker = el("div", { class: "ticker" });
  if (label) {
    ticker.append(filterRow(label, settings.onClearFilter));
  }
  if (!rows.length) {
    ticker.append(
      label
        ? emptyState("Nothing matches this filter", "Clear it to see the whole stream again.")
        : emptyState(
            "No fleet activity yet",
            "Spans and model calls stream here while the job runs."
          )
    );
    target.append(ticker);
    return;
  }
  rows.forEach((event) => ticker.append(tickerRow(event, selectedSeq, onSelect)));
  target.append(ticker);
  restoreScroll(ticker, anchor);
}
