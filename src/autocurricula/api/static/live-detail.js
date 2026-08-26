import { clear, el, emptyState, formatDateTime, pill } from "./render.js";
import { KIND_LABELS, classifyEvent, durationText, toneOf } from "./live-kinds.js";

const SCALAR_FIELDS = [
  ["Agent", "agent_id"],
  ["Principal", "principal"],
  ["Student", "student_id"],
  ["Stage", "stage"],
  ["Span", "span_id"],
  ["Parent span", "parent_span_id"],
];

function detailCell(label, value) {
  return el("div", {}, [
    el("span", { class: "list-sub", text: label }),
    el("span", { class: "mono", text: value }),
  ]);
}

function scalarGrid(event) {
  return el(
    "div",
    { class: "detail-grid" },
    SCALAR_FIELDS.map(([label, key]) => detailCell(label, event[key] ? String(event[key]) : "—"))
  );
}

function attributeGrid(attributes) {
  const entries = Object.entries(attributes);
  if (!entries.length) {
    return el("p", { class: "list-sub", text: "No attributes recorded on this event." });
  }
  return el(
    "div",
    { class: "detail-grid" },
    entries.map(([key, value]) => detailCell(key, String(value)))
  );
}

function appendExchange(detail, llm) {
  const inbound = Number(llm.input_tokens) || 0;
  const outbound = Number(llm.output_tokens) || 0;
  const total = Number(llm.total_tokens) || inbound + outbound;
  detail.append(el("p", { class: "section-title", text: "Model exchange" }));
  detail.append(
    el("div", { class: "detail-grid" }, [
      detailCell("Model", llm.model || "—"),
      detailCell("Finish reason", llm.finish_reason || "—"),
      detailCell("Tokens", `${inbound} in / ${outbound} out / ${total} total`),
    ])
  );
  detail.append(el("p", { class: "section-title", text: "Prompt (excerpt)" }));
  detail.append(el("pre", { class: "payload-block mono", text: llm.request_excerpt || "(empty)" }));
  detail.append(el("p", { class: "section-title", text: "Response (excerpt)" }));
  detail.append(el("pre", { class: "payload-block mono", text: llm.response_excerpt || "(empty)" }));
  if (llm.truncated) {
    detail.append(
      el("p", {
        class: "list-sub",
        text: "Excerpt truncated for transport — the full payload stays in the Cloud Trace span.",
      })
    );
  }
}

function statusTone(status) {
  if (status === "error") {
    return "failed";
  }
  return status === "running" ? "running" : "succeeded";
}

function payloadScrolls(target, event) {
  if (!event || target.dataset.eventSeq !== String(event.seq)) {
    return [];
  }
  return [...target.querySelectorAll(".payload-block")].map((block) => block.scrollTop);
}

function restorePayloadScrolls(target, offsets) {
  if (!offsets.length) {
    return;
  }
  target.querySelectorAll(".payload-block").forEach((block, index) => {
    block.scrollTop = offsets[index] || 0;
  });
}

export function renderEventDetail(target, event, meta) {
  const offsets = payloadScrolls(target, event);
  target.dataset.eventSeq = event ? String(event.seq) : "";
  clear(target);
  if (!event) {
    target.append(
      emptyState("No event selected", "Pick a row in the ticker to inspect the exact payload.")
    );
    return;
  }
  const kind = classifyEvent(event);
  const detail = el("div", { class: "event-detail" });
  detail.append(
    el("div", { class: "list-title" }, [
      el("span", { class: "mono", text: event.name }),
      pill(String(event.status), statusTone(event.status)),
    ])
  );
  detail.append(
    el("div", { class: "list-sub" }, [
      pill(KIND_LABELS[kind], toneOf(event, kind)),
      el("span", { text: `#${event.seq}` }),
      el("span", { text: formatDateTime(event.recorded_at) }),
      el("span", { text: durationText(event.duration_ms) || "—" }),
    ])
  );
  detail.append(scalarGrid(event));
  detail.append(el("p", { class: "section-title", text: "Attributes" }));
  detail.append(attributeGrid(event.attributes || {}));
  if (event.llm) {
    appendExchange(detail, event.llm);
  }
  const traceUrl = meta && meta.cloudTraceUrl;
  if (traceUrl) {
    detail.append(
      el("a", {
        class: "ghost",
        href: traceUrl,
        target: "_blank",
        rel: "noreferrer",
        text: "Open this trace in Cloud Trace",
      })
    );
  }
  target.append(detail);
  restorePayloadScrolls(target, offsets);
}
