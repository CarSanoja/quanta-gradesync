import { clear, el, emptyState, formatDateTime, formatNumber, formatPercent, table } from "./render.js";

const POLL_INTERVAL_MS = 5000;

function competencyCell(codes) {
  if (!codes.length) {
    return el("span", { class: "upload-note", text: "none" });
  }
  return el("span", { class: "mono", text: codes.join(" ") });
}

function recordRow(record) {
  return el("tr", {}, [
    el("td", {}, [
      el("span", { class: "mono", text: record.student_id }),
      el("div", { class: "list-sub", text: record.job_id }),
    ]),
    el("td", { text: record.class_id || "—" }),
    el("td", { text: record.subject }),
    el("td", { class: "numeric", text: formatNumber(record.total_score, 1) }),
    el("td", { class: "numeric", text: formatPercent(record.percentage) }),
    el("td", {}, competencyCell(record.competency_codes)),
    el("td", { class: "numeric", text: formatDateTime(record.written_at) }),
  ]);
}

export function renderSisRecords(target, payload) {
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
        { label: "Written", numeric: true },
      ],
      payload.items.map(recordRow)
    )
  );
}

export function createSisController({ dom, guard, getJson, endpoints }) {
  let timer = null;
  let loading = false;

  async function load() {
    if (loading) {
      return;
    }
    loading = true;
    try {
      const payload = await guard(() => getJson(endpoints.sisRecords()));
      if (payload) {
        dom.sisCount.textContent = `${payload.count} record${payload.count === 1 ? "" : "s"} · ${payload.source}`;
        renderSisRecords(dom.sisRecords, payload);
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
    timer = window.setInterval(load, POLL_INTERVAL_MS);
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
