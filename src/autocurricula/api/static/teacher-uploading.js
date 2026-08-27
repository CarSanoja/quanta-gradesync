import { el } from "/console/assets/render.js";
import { plural } from "/teacher/assets/teacher-format.js";
import { lotFields } from "/teacher/assets/teacher-intake.js";
import { pairSection, troubleSections, unnamedSection } from "/teacher/assets/teacher-staging.js";
import { uploads, uploadState } from "/teacher/assets/teacher-upload.js";

const STAGES = ["named", "sending", "arrived"];
const ARRIVED = new Set(["received", "skipped"]);

function stageOf(row) {
  if (row.state === "failed") return -2;
  if (ARRIVED.has(row.state)) return 3;
  if (row.state === "sending") return 1;
  if (row.state === "ready") return 1;
  return 0;
}

function stageLabel(row) {
  if (row.state === "failed") return row.status || "did not go through";
  if (row.state === "skipped") return "kept the scan already saved";
  if (row.state === "received") return "arrived";
  if (row.state === "sending") return "sending";
  if (row.state === "needs-name") return "needs a name from you";
  if (row.state === "held") return "held back";
  if (row.state === "paused") return "waiting on your answer";
  return "queued";
}

function dots(row) {
  const reached = stageOf(row);
  return el("span", { class: "file-dots" }, STAGES.map((name, index) => {
    let tone = "";
    if (reached === -2 && index >= 1) {
      tone = " is-failed";
    } else if (reached > index) {
      tone = " is-done";
    } else if (reached === index) {
      tone = " is-now";
    }
    return el("span", { class: `file-dot${tone}`, title: name });
  }));
}

function fileRow(row) {
  const named = Boolean(row.studentId);
  const tone = row.state === "failed" ? " is-failed" : named ? "" : " is-unnamed";
  return el("li", { class: "file-row" }, [
    el("div", { class: "file-who" }, [
      el("p", { class: `file-name${tone}`, text: row.student || row.name || "Not named yet" }),
      el("p", { class: "file-meta", text: `${row.label} · ${stageLabel(row)}` }),
    ]),
    dots(row),
  ]);
}

function percent(state) {
  if (!state.total) {
    return 0;
  }
  const done = state.received + state.skipped;
  const moving = state.sending * 0.5;
  return Math.min(100, Math.round(((done + moving) / state.total) * 100));
}

function stageCounts(state) {
  const queued = state.total - state.received - state.skipped - state.sending
    - state.failed.length - state.needsName.length - state.held.length;
  const counts = [
    ["waiting on you", state.needsName.length + state.held.length],
    ["queued", Math.max(queued, 0)],
    ["sending", state.sending],
    ["arrived", state.received],
    ["already saved", state.skipped],
    ["did not go through", state.failed.length],
  ];
  return el("ul", { class: "stage-counts" }, counts
    .filter(([, value]) => value > 0)
    .map(([label, value]) =>
      el("li", {}, [el("b", { text: String(value) }), el("span", { text: ` ${label}` })])));
}


function arrivedLine(state) {
  if (state.received >= state.total && state.total > 0) {
    return `All ${state.total} ${plural(state.total, "file", "files")} arrived.`;
  }
  if (state.sent >= state.total && state.skipped > 0) {
    return `${state.received} of ${state.total} arrived; ${state.skipped} kept the scan already saved.`;
  }
  return `${state.received} of ${state.total} ${plural(state.total, "file has", "files have")} arrived.`;
}

function noteLine(state) {
  if (state.awaitingLot) {
    return "Fill in the three boxes above and sending starts on its own.";
  }
  if (state.running) {
    return "Sending is in progress. Keep this page open until every file has arrived.";
  }
  if (state.failed.length) {
    return "Some files were not sent. Try those again before you leave this page.";
  }
  if (state.sent === state.total && state.total > 0) {
    return state.skipped
      ? "Every file is accounted for. You can safely leave this page."
      : "Every file has arrived. You can safely leave this page.";
  }
  return "Not sent yet. Complete what the page asks for below.";
}

function bar(state) {
  const pct = (share) => `width:${state.total ? Math.round(share * 100) : 0}%`;
  return el("div", {
    class: "progress-track",
    "aria-label": `${state.received} received, ${state.sending} sending, ${state.failed.length} failed`,
  }, [
    el("span", { class: "progress-fill is-received", style: pct(state.received / state.total) }),
    el("span", { class: "progress-fill is-kept", style: pct(state.skipped / state.total) }),
    el("span", { class: "progress-fill is-sending", style: pct(state.sending / state.total) }),
    el("span", { class: "progress-fill is-failed", style: pct(state.failed.length / state.total) }),
  ]);
}

export function renderUploading(host, ctx) {
  const state = uploadState();
  host.className = "screen";
  host.append(
    el("p", { class: "eyebrow", text: "Sending this batch" }),
    el("div", { class: "pipe-figure" }, [
      el("span", { class: "pipe-pct", text: `${percent(state)}%` }),
      el("span", { class: "pipe-summary", text: arrivedLine(state) }),
    ]),
    bar(state),
    stageCounts(state),
    el("p", { class: "note", style: "margin-bottom:2.5rem", text: noteLine(state) }),
    lotFields(ctx)
  );
  if (uploads.pair) {
    host.append(pairSection(ctx));
  }
  if (state.needsName.length) {
    host.append(unnamedSection(ctx, state.needsName));
  }
  troubleSections(ctx, state).forEach((node) => host.append(node));
  if (state.total) {
    host.append(
      el("h2", { class: "section-title", text: "File by file" }),
      el("p", {
        class: "section-note",
        text: "Each line is one scan on its way. Nothing here is graded yet.",
      }),
      el("ul", { class: "file-rows" }, uploads.rows.map(fileRow))
    );
  }
  host.append(el("div", { class: "button-row", style: "margin-top:2.25rem" }, [
    el("button", {
      class: "primary",
      type: "button",
      text: state.running
        ? `Sending ${state.received} of ${state.total}…`
        : "Done — start grading",
      disabled: state.running,
      onclick: () => ctx.goGrading(),
    }),
  ]));
}
