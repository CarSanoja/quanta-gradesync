import { el } from "/console/assets/render.js";
import { pitchLine, valueBand } from "/teacher/assets/teacher-value.js";
import {
  examCount, fmt, plural, prettyName, prettySubject, timeAgo, whenSent,
} from "/teacher/assets/teacher-format.js";
import { renderHeld } from "/teacher/assets/teacher-held.js";
import { renderUploading } from "/teacher/assets/teacher-uploading.js";

function dropzone(ctx, title, hint, label) {
  const zone = el("div", { class: "dropzone" }, [
    el("p", { class: "dropzone-title", text: title }),
    el("p", { class: "dropzone-hint", text: hint }),
    el("button", { class: "primary", type: "button", text: label, onclick: () => ctx.pickFiles() }),
  ]);
  zone.addEventListener("click", (event) => {
    if (event.target === zone || event.target.tagName === "P") {
      ctx.pickFiles();
    }
  });
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.add("is-dragover");
  }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragover");
  }));
  zone.addEventListener("drop", (event) => {
    if (event.dataTransfer && event.dataTransfer.files.length) {
      ctx.stageFiles(event.dataTransfer.files);
    }
  });
  return zone;
}

export function renderHome(host, ctx) {
  const batch = ctx.batch;
  host.className = "screen";
  host.append(
    el("p", { class: "eyebrow", text: batch ? batch.assessment : "Your class" }),
    el("h1", { class: "display", text: "Nothing needs you." }),
    el("p", {
      class: "lede",
      text: batch
        ? `All ${examCount(batch.in_gradebook)} from ${batch.assessment} are in the gradebook, and `
          + "your students can see their feedback. When something needs your decision, it will be "
          + "waiting here."
        : "Nothing is waiting for your decision. Send the scans of an exam and grading starts on "
          + "its own — when something needs you, it will be waiting here.",
    }),
    batch ? valueBand(batch) : pitchLine(),
    dropzone(ctx, "Drop your scans here",
      "Photos or PDFs, as many as you like. You never have to rename a file on your computer — "
      + "you can type each student's name on this page.",
      "Choose files from your computer")
  );
  if (!batch) {
    return;
  }
  const when = whenSent(batch.started_at);
  host.append(el("div", { class: "last-sent" }, [
    el("span", {
      text: `Last sent${when ? ` ${when}` : ""} — ${examCount(batch.received)}, ${batch.assessment}.`,
    }),
    el("button", { class: "linkish", type: "button", text: "See those grades", onclick: () => ctx.goGrades() }),
  ]));
}

function statusLine(kind, glyph, text) {
  return el("li", { class: `is-${kind}` }, [
    el("span", { class: "glyph", "aria-hidden": "true", text: glyph }),
    el("span", { text }),
  ]);
}

export function renderGrading(host, ctx) {
  const batch = ctx.batch;
  const when = whenSent(batch.started_at);
  const waiting = batch.waiting_for_you;
  const lines = [
    statusLine("done", "✓", `${batch.in_gradebook} ${plural(batch.in_gradebook, "is", "are")} already in the gradebook`),
  ];
  if (waiting) {
    lines.push(statusLine("waiting", "!", `${waiting} ${plural(waiting, "is", "are")} waiting for you`));
  }
  lines.push(statusLine("pending", "◔",
    `${batch.still_grading} ${plural(batch.still_grading, "is", "are")} still being graded`));
  if (batch.could_not_grade) {
    lines.push(statusLine("failed", "×",
      `${batch.could_not_grade} could not be graded and ${plural(batch.could_not_grade, "needs", "need")} marking by hand`));
  }
  host.className = "screen";
  host.append(
    el("p", { class: "eyebrow", text: `${batch.assessment}${when ? ` · sent ${when}` : ""}` }),
    el("h1", { class: "display is-small", text: `We received ${examCount(batch.received)}.` }),
    el("ul", { class: "status-lines" }, lines)
  );
  if (waiting) {
    host.append(el("button", {
      class: "primary",
      type: "button",
      text: `Review the ${waiting} waiting for you`,
      onclick: () => ctx.goReview(),
    }));
  }
  host.append(el("p", {
    class: "note",
    style: "margin-top:1.375rem",
    text: "This page keeps itself up to date. You can close it and come back — grading carries on "
      + "without you.",
  }));
}

function classAverage(ctx) {
  const batch = ctx.batch;
  const records = (ctx.batchRecords || []).filter((record) => record.job_id === batch.job_id
    && record.total_score !== null && record.percentage !== null);
  if (!records.length || records.length < batch.in_gradebook) {
    return null;
  }
  const score = records.reduce((sum, record) => sum + record.total_score, 0) / records.length;
  const percent = records.reduce((sum, record) => sum + record.percentage, 0) / records.length;
  const ceilings = records
    .filter((record) => record.percentage > 0)
    .map((record) => (100 * record.total_score) / record.percentage);
  const ceiling = ceilings.length ? ceilings.reduce((sum, value) => sum + value, 0) / ceilings.length : null;
  return ceiling
    ? `${fmt(score)} of ${fmt(ceiling)} · ${Math.round(percent)}%`
    : `${Math.round(percent)}%`;
}

export function renderSettled(host, ctx) {
  const batch = ctx.batch;
  const average = classAverage(ctx);
  const rows = [
    ["Graded automatically", examCount(batch.graded_automatically)],
    ["Decided by you", examCount(batch.decided_by_you)],
  ];
  if (batch.could_not_grade) {
    rows.push(["Could not be graded", examCount(batch.could_not_grade)]);
  }
  if (average) {
    rows.push(["Class average", average]);
  }
  host.className = "screen";
  host.append(
    el("span", { class: "settled-mark", "aria-hidden": "true", text: "✓" }),
    el("h1", { class: "display", text: `${batch.assessment} is finished.` }),
    el("p", {
      class: "lede",
      text: "Every exam is in the gradebook and your students can see their feedback. There is "
        + "nothing left waiting for you.",
    }),
    el("ul", { class: "tally" }, rows.map(([label, value]) => el("li", {}, [
      el("span", { text: label }),
      el("span", { text: value }),
    ]))),
    el("div", { class: "button-row" }, [
      el("button", { class: "primary", type: "button", text: "See the grades", onclick: () => ctx.goGrades() }),
      el("button", { class: "secondary", type: "button", text: "Send more scans", onclick: () => ctx.goHome() }),
    ])
  );
}

function gradeRow(record) {
  const max = record.percentage ? (100 * record.total_score) / record.percentage : null;
  const detail = [prettySubject(record.subject), prettyName(record.term || "")]
    .filter(Boolean)
    .concat(`in the gradebook ${timeAgo(record.written_at)}`)
    .join(" · ");
  const score = record.total_score === null
    ? "graded"
    : `${fmt(record.total_score)}${max ? ` of ${fmt(max)}` : ""}`
      + `${record.percentage === null ? "" : ` · ${Math.round(record.percentage)}%`}`;
  return el("li", {}, [
    el("div", { class: "grade-who" }, [
      el("p", { class: "grade-student", text: prettyName(record.student_id) }),
      el("p", { class: "grade-detail", text: detail }),
    ]),
    el("div", { class: "grade-figure" }, [
      el("p", { class: "grade-score", text: score }),
      record.competency_codes.length
        ? el("p", { class: "grade-cite", text: record.competency_codes.join(" · ") })
        : null,
    ]),
  ]);
}

export function renderGrades(host, ctx) {
  const query = String(ctx.queries.grades || "").trim().toLowerCase();
  const found = ctx.records.filter((record) =>
    !query || prettyName(record.student_id).toLowerCase().includes(query));
  const input = el("input", {
    type: "search",
    id: "grades-search",
    placeholder: "Ana, Camila, Julián…",
    autocomplete: "off",
    oninput: (event) => ctx.setQuery("grades", event.target.value),
  });
  input.value = ctx.queries.grades || "";
  host.className = "screen is-wide";
  host.append(
    el("h1", { class: "display is-small", text: "Recent grades" }),
    el("label", { class: "finder", for: "grades-search" }, [
      el("span", { text: "Search by student name" }),
      input,
    ])
  );
  if (!ctx.records.length) {
    host.append(el("p", {
      class: "empty-line",
      text: "No grades are in the gradebook yet. They appear here the moment grading finishes.",
    }));
    return;
  }
  host.append(el("ul", { class: "grades" }, found.map(gradeRow)));
  host.append(el("p", {
    class: "grades-foot",
    text: query
      ? `${found.length} of ${ctx.records.length} shown.`
      : `Showing the ${ctx.records.length} most recent. Type a name to find a student.`,
  }));
}

export function screenBuilders() {
  return {
    home: renderHome,
    uploading: renderUploading,
    grading: renderGrading,
    held: renderHeld,
    settled: renderSettled,
    grades: renderGrades,
  };
}
