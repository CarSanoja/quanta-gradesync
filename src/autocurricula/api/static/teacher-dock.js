import { clear, el } from "/console/assets/render.js";
import { plural } from "/teacher/assets/teacher-format.js";
import { uploads } from "/teacher/assets/teacher-upload.js";

// Sending used to take over the page, which meant a teacher with three sections
// had to finish one, navigate back, and start again. The dock keeps every batch
// she has sent in this sitting visible beside the drop zone, so the next one is
// a drag away and the only button she ever needs is the one that opens grades.

function percent(batch) {
  if (!batch.total) {
    return 0;
  }
  return Math.min(100, Math.round(((batch.received + batch.skipped) / batch.total) * 100));
}

function statusLine(batch) {
  if (batch.running) {
    return `${batch.received} of ${batch.total} sent`;
  }
  if (batch.failed) {
    return `${batch.failed} ${plural(batch.failed, "file", "files")} did not go through`;
  }
  if (batch.skipped) {
    return `${batch.received} arrived · ${batch.skipped} already saved`;
  }
  return `${batch.total} ${plural(batch.total, "exam", "exams")} sent`;
}

function sectionOf(lotCode) {
  const parts = lotCode.split("_");
  return parts.length >= 3 ? parts[2] : lotCode;
}

function card(batch, onOpen) {
  const tone = batch.running ? " is-running" : batch.failed ? " is-failed" : " is-done";
  return el("li", { class: `dock-card${tone}` }, [
    el("p", { class: "dock-section", text: sectionOf(batch.lotCode) }),
    el("p", { class: "dock-lot", text: batch.lotCode }),
    el("div", { class: "dock-track" }, [
      el("span", { class: "dock-fill", style: `width:${percent(batch)}%` }),
    ]),
    el("p", { class: "dock-status", text: statusLine(batch) }),
    // This button used to sit at the bottom of a screen that took over the page
    // while the scans moved. It belongs to the batch, so it lives on the batch.
    el("button", {
      class: `${batch.running ? "quiet" : "primary"} dock-open`,
      type: "button",
      text: batch.running ? `Sending ${batch.received} of ${batch.total}…` : "Done — start grading",
      disabled: batch.running,
      onclick: () => onOpen(batch.lotCode),
    }),
  ]);
}

export function paintDock(host, onOpen) {
  const batches = uploads.batches;
  host.hidden = batches.length === 0;
  clear(host);
  if (!batches.length) {
    return;
  }
  const sent = batches.reduce((count, batch) => count + batch.received, 0);
  const running = batches.some((batch) => batch.running);
  host.append(
    el("p", { class: "dock-eyebrow", text: "Sent from this page" }),
    el("p", {
      class: "dock-total",
      text: `${sent} ${plural(sent, "exam", "exams")} · ${batches.length} `
        + plural(batches.length, "batch", "batches"),
    }),
    el("ul", { class: "dock-list" }, batches.map((batch) => card(batch, onOpen))),
    el("p", {
      class: "dock-note",
      text: running
        ? "Keep this page open. You can drop the next section now."
        : "Drop the next section whenever you like — nothing here needs you.",
    })
  );
}
