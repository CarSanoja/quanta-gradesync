import { clear, el, emptyState, formatDateTime, formatNumber, formatPercent, table } from "./render.js";

const POLL_INTERVAL_MS = 5000;
const PAGE_LIMIT = 50;

function navigate(name, argument) {
  const go = window[name];
  if (typeof go === "function") {
    go(argument);
  }
}

function competencyCell(codes) {
  if (!codes.length) {
    return el("span", { class: "upload-note", text: "none" });
  }
  return el("span", { class: "mono", text: codes.join(" ") });
}

function batchCell(record, onFilterJob) {
  return el("div", { class: "row-actions is-left" }, [
    el("button", {
      class: "ghost batch-link",
      type: "button",
      text: record.job_id,
      onclick: () => onFilterJob(record.job_id),
    }),
    el("button", {
      class: "ghost batch-link",
      type: "button",
      text: "Open the batch",
      onclick: () => navigate("goToJobsBatch", record.job_id),
    }),
  ]);
}

function recordRow(record, onFilterJob) {
  return el("tr", {}, [
    el("td", {}, [
      el("span", { class: "mono", text: record.student_id }),
      batchCell(record, onFilterJob),
    ]),
    el("td", { text: record.class_id || "—" }),
    el("td", { text: record.subject }),
    el("td", { class: "numeric", text: formatNumber(record.total_score, 1) }),
    el("td", { class: "numeric", text: formatPercent(record.percentage) }),
    el("td", {}, competencyCell(record.competency_codes)),
    el("td", {}, [
      el("span", { class: "mono", text: record.prompt_variant_id || "—" }),
      el("div", { class: "list-sub", text: formatDateTime(record.graded_at) }),
    ]),
    el("td", { class: "numeric", text: formatDateTime(record.written_at) }),
  ]);
}

export function renderSisRecords(target, payload, onFilterJob) {
  clear(target);
  if (!payload.items.length) {
    target.append(
      emptyState(
        "No grades written yet",
        "Records appear here the moment the engine writes them to the SIS."
      )
    );
    return;
  }
  target.append(
    table(
      [
        { label: "Student" },
        { label: "Class" },
        { label: "Subject" },
        { label: "Total", numeric: true },
        { label: "%", numeric: true },
        { label: "Competencies" },
        { label: "Graded by" },
        { label: "Written", numeric: true },
      ],
      payload.items.map((record) => recordRow(record, onFilterJob))
    )
  );
}

export function createSisController({ dom, guard, getJson, endpoints }) {
  let timer = null;
  let loading = false;
  let jobFilter = null;

  function paintCount(payload) {
    const capped = payload.count >= PAGE_LIMIT ? " · newest 50 shown" : "";
    clear(dom.sisCount);
    dom.sisCount.append(
      el("span", {
        text: `${payload.count} record${payload.count === 1 ? "" : "s"}${capped} · source ${payload.source}`,
      })
    );
    if (!jobFilter) {
      return;
    }
    dom.sisCount.append(el("span", { class: "mono", text: ` · batch ${jobFilter}` }));
    dom.sisCount.append(
      el("button", {
        class: "ghost batch-link",
        type: "button",
        text: "Show all batches",
        onclick: () => load(null),
      })
    );
  }

  async function load(jobId) {
    if (jobId !== undefined) {
      jobFilter = jobId || null;
    }
    if (loading) {
      return;
    }
    loading = true;
    try {
      const payload = await guard(() => getJson(endpoints.sisRecords(jobFilter, PAGE_LIMIT)));
      if (payload) {
        paintCount(payload);
        renderSisRecords(dom.sisRecords, payload, (id) => load(id));
      }
    } finally {
      loading = false;
    }
  }

  function start() {
    if (timer !== null) {
      return;
    }
    dom.sisPoll.classList.add("is-live");
    load();
    timer = window.setInterval(() => load(), POLL_INTERVAL_MS);
  }

  function stop() {
    if (timer !== null) {
      window.clearInterval(timer);
      timer = null;
    }
    dom.sisPoll.classList.remove("is-live");
  }

  return { start, stop, load };
}
