import { clear, el, pill } from "./render.js";

let selectedSpanId = null;

export function formatMs(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function tokensOf(span) {
  const attributes = span.attributes || {};
  const total = attributes["gen_ai.usage.tokens"];
  if (typeof total === "number") {
    return `${total} tok`;
  }
  const input = attributes["gen_ai.usage.input_tokens"];
  const output = attributes["gen_ai.usage.output_tokens"];
  if (typeof input === "number" || typeof output === "number") {
    return `${input || 0}+${output || 0} tok`;
  }
  return "";
}

function detailCell(label, value) {
  return el("div", {}, [
    el("span", { class: "list-sub", text: label }),
    el("span", { class: "mono", text: value }),
  ]);
}

function spanDetail(span) {
  const block = el("div", { class: "span-detail" });
  block.append(el("p", { class: "section-title", text: "Selected span" }));
  block.append(
    el("div", { class: "detail-grid" }, [
      detailCell("Name", span.name),
      detailCell("Stage", span.stage || "—"),
      detailCell("Status", span.status || "—"),
      detailCell("Took", formatMs(span.duration_ms)),
      detailCell("Span id", span.span_id),
      detailCell("Parent span", span.parent_id || "—"),
    ])
  );
  const entries = Object.entries(span.attributes || {});
  block.append(el("p", { class: "section-title", text: "Span attributes" }));
  block.append(
    entries.length
      ? el(
          "div",
          { class: "detail-grid" },
          entries.map(([key, value]) => detailCell(key, String(value)))
        )
      : el("p", { class: "list-sub", text: "No attributes were recorded on this span." })
  );
  return block;
}

function spanRow(span, depth, maxDuration, onSelect) {
  const width = maxDuration > 0 ? Math.max(1.5, (span.duration_ms / maxDuration) * 100) : 1.5;
  const failed = span.status === "error";
  const selected = span.span_id === selectedSpanId;
  return el(
    "button",
    {
      type: "button",
      class: `span-row${selected ? " is-selected" : ""}`,
      onclick: () => onSelect(span.span_id),
    },
    [
      el("div", { class: "span-name", style: `padding-left:${depth * 16}px` }, [
        el("span", { class: "mono", text: span.name }),
        span.stage ? pill(span.stage.toLowerCase(), failed ? "failed" : "succeeded") : null,
        failed ? el("span", { class: "span-error", text: "error" }) : null,
      ]),
      el(
        "div",
        { class: "span-bar-track" },
        el("div", { class: `span-bar${failed ? " is-error" : ""}`, style: `width:${width}%` })
      ),
      el("span", { class: "span-duration", text: formatMs(span.duration_ms) }),
      el("span", { class: "span-tokens", text: tokensOf(span) }),
    ]
  );
}

function buildTree(spans, onSelect) {
  const children = new Map();
  const ids = new Set(spans.map((span) => span.span_id));
  spans.forEach((span) => {
    const parent = span.parent_id && ids.has(span.parent_id) ? span.parent_id : null;
    if (!children.has(parent)) {
      children.set(parent, []);
    }
    children.get(parent).push(span);
  });
  const maxDuration = Math.max(0, ...spans.map((span) => span.duration_ms));
  const tree = el("div", { class: "span-tree" });
  const walk = (parentId, depth) => {
    (children.get(parentId) || []).forEach((span) => {
      tree.append(spanRow(span, depth, maxDuration, onSelect));
      walk(span.span_id, depth + 1);
    });
  };
  walk(null, 0);
  return tree;
}

export function renderSpanTree(target, spans) {
  const host = el("div", { class: "span-host" });
  const paint = () => {
    clear(host);
    const select = (spanId) => {
      selectedSpanId = selectedSpanId === spanId ? null : spanId;
      paint();
    };
    host.append(buildTree(spans, select));
    const selected = spans.find((span) => span.span_id === selectedSpanId);
    if (selected) {
      host.append(spanDetail(selected));
    }
  };
  paint();
  target.append(host);
}
