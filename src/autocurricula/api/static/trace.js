import { clear, el, emptyState, formatDateTime, metaRow, pill } from "./render.js";

const POLL_INTERVAL_MS = 2500;
const TERMINAL_STAGES = new Set(["completed", "failed"]);

function formatMs(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function tokensOf(span) {
  const total = span.attributes["gen_ai.usage.tokens"];
  if (typeof total === "number") {
    return `${total} tok`;
  }
  const input = span.attributes["gen_ai.usage.input_tokens"];
  const output = span.attributes["gen_ai.usage.output_tokens"];
  if (typeof input === "number" || typeof output === "number") {
    return `${input || 0}+${output || 0} tok`;
  }
  return "";
}

function spanRow(span, depth, maxDuration) {
  const width = maxDuration > 0 ? Math.max(1.5, (span.duration_ms / maxDuration) * 100) : 1.5;
  const failed = span.status === "error";
  return el("div", { class: "span-row" }, [
    el("div", { class: "span-name", style: `padding-left:${depth * 16}px` }, [
      el("span", { class: "mono", text: span.name }),
      span.stage ? pill(span.stage, failed ? "failed" : "succeeded") : null,
      failed ? el("span", { class: "span-error", text: "error" }) : null,
    ]),
    el("div", { class: "span-bar-track" },
      el("div", { class: `span-bar${failed ? " is-error" : ""}`, style: `width:${width}%` })),
    el("span", { class: "span-duration", text: formatMs(span.duration_ms) }),
    el("span", { class: "span-tokens", text: tokensOf(span) }),
  ]);
}

export function renderSpanTree(target, spans) {
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
      tree.append(spanRow(span, depth, maxDuration));
      walk(span.span_id, depth + 1);
    });
  };
  walk(null, 0);
  target.append(tree);
}

function metricsTable(metrics) {
  const head = el("div", { class: "span-row" }, [
    el("span", { class: "upload-note", text: "stage" }),
    el("span", { class: "upload-note", text: "calls" }),
    el("span", { class: "span-duration upload-note", text: "p95" }),
    el("span", { class: "span-tokens upload-note", text: "tokens" }),
  ]);
  const rows = metrics.stages.map((stage) =>
    el("div", { class: "span-row" }, [
      el("span", { class: "mono", text: stage.stage + (stage.errors ? ` · ${stage.errors} err` : "") }),
      el("span", { text: String(stage.count) }),
      el("span", { class: "span-duration", text: formatMs(stage.latency_p95_ms) }),
      el("span", { class: "span-tokens", text: `${stage.total_tokens} tok` }),
    ])
  );
  return el("div", { class: "span-tree" }, [head, ...rows]);
}

function auditTail(events) {
  return el("ul", { class: "audit-tail" }, events.slice().reverse().map((event) =>
    el("li", { class: `audit-event${event.error ? " is-error" : ""}` }, [
      el("span", { class: "mono", text: formatDateTime(event.recorded_at) }),
      el("span", { text: event.error ? `${event.stage || "?"} · ${event.error}` : event.stage || "—" }),
      el("span", { class: "mono", text: `${event.span_count} spans · ${event.total_tokens} tok` }),
    ])
  ));
}

export function renderTraceDetail(target, trace) {
  clear(target);
  if (!trace) {
    target.append(emptyState("Select a job", "Its stage progress and span tree appear here."));
    return;
  }
  target.append(el("span", { class: "list-title" }, [
    el("span", { class: "mono", text: trace.job_id }),
    pill(trace.stage, trace.stage === "completed" ? "succeeded" : trace.stage),
  ]));
  target.append(metaRow([
    el("span", { class: "mono", text: `trace ${trace.trace_id}` }),
    trace.recorded_at ? `audited ${formatDateTime(trace.recorded_at)}` : "audit pending",
  ]));
  if (trace.error) {
    target.append(el("ul", { class: "reasons" }, el("li", { class: "reason", text: trace.error })));
  }
  target.append(el("p", { class: "section-title", text: "Pipeline stages" }));
  target.append(el("div", { class: "stage-track" },
    trace.stages.map((stage) => pill(`${stage.name} · ${stage.status}`, stage.status))));
  target.append(el("p", { class: "section-title", text: "Span tree" }));
  if (trace.spans.length) {
    renderSpanTree(target, trace.spans);
  } else {
    target.append(emptyState("No spans persisted yet", "The audit event lands when the job finishes a run."));
  }
  if (trace.metrics) {
    target.append(el("p", { class: "section-title", text: "Metrics snapshot" }));
    target.append(metricsTable(trace.metrics));
  }
  target.append(el("p", { class: "section-title", text: "Audit tail" }));
  if (trace.events.length) {
    target.append(auditTail(trace.events));
  } else {
    target.append(emptyState("No audit events", "Raw audit entries appear here as the engine writes them."));
  }
}

export function renderTraceJobs(target, jobs, activeId, onSelect) {
  clear(target);
  if (!jobs.length) {
    target.append(emptyState("No jobs yet", "Ingest a batch and it appears here within seconds."));
    return;
  }
  const list = el("div", { class: "list" });
  jobs.forEach((job) => {
    list.append(el("button", {
      type: "button",
      class: `list-item${job.job_id === activeId ? " is-active" : ""}`,
      onclick: () => onSelect(job.job_id),
    }, [
      el("span", { class: "list-title" }, [
        el("span", { class: "mono", text: job.job_id }),
        pill(job.stage, job.stage === "completed" ? "succeeded" : job.stage),
      ]),
      metaRow([`${job.subject} · ${job.class_id}`, `updated ${formatDateTime(job.updated_at)}`]),
    ]));
  });
  target.append(list);
}

export function createTraceController({ dom, guard, getJson, endpoints }) {
  const state = { jobs: [], activeJobId: null, timer: null };

  function indicator(live, label) {
    dom.tracePoll.classList.toggle("is-live", live);
    dom.traceStatus.textContent = label;
  }

  async function loadDetail() {
    if (!state.activeJobId) {
      renderTraceDetail(dom.traceDetail, null);
      return;
    }
    const trace = await guard(() => getJson(endpoints.trace(state.activeJobId)));
    if (!trace || trace.job_id !== state.activeJobId) {
      return;
    }
    renderTraceDetail(dom.traceDetail, trace);
    if (TERMINAL_STAGES.has(trace.stage)) {
      stopTimer();
      indicator(false, `settled · ${trace.stage}`);
    }
  }

  async function tick() {
    const payload = await guard(() => getJson(endpoints.jobs()));
    if (payload) {
      state.jobs = payload.items;
      if (!state.activeJobId && state.jobs.length) {
        state.activeJobId = state.jobs[0].job_id;
      }
      renderTraceJobs(dom.traceJobs, state.jobs, state.activeJobId, select);
    }
    await loadDetail();
  }

  function stopTimer() {
    if (state.timer !== null) {
      window.clearInterval(state.timer);
      state.timer = null;
    }
  }

  function startTimer() {
    stopTimer();
    indicator(true, "polling");
    state.timer = window.setInterval(tick, POLL_INTERVAL_MS);
    tick();
  }

  function select(jobId) {
    state.activeJobId = jobId;
    renderTraceJobs(dom.traceJobs, state.jobs, state.activeJobId, select);
    startTimer();
  }

  function start() {
    startTimer();
  }

  function stop() {
    stopTimer();
    indicator(false, "");
  }

  return { start, stop, load: tick };
}
