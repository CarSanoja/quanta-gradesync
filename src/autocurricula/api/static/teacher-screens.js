import { el } from "/console/assets/render.js";
import { gradeRow, openGradeId, openGradeKey } from "/teacher/assets/teacher-grades.js";
import { pitchLine, valueBand } from "/teacher/assets/teacher-value.js";
import {
  examCount, fmt, plural, prettyName, prettySubject, timeAgo, whenSent,
} from "/teacher/assets/teacher-format.js";
import { fileStem } from "/teacher/assets/teacher-filenames.js";
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
  const complete = batch && batch.settled && batch.in_gradebook >= batch.received;
  const lede = !batch
    ? "Nothing is waiting for your decision. Send the scans of an exam and grading starts on "
      + "its own — when something needs you, it will be waiting here."
    : complete
      ? `All ${examCount(batch.in_gradebook)} from ${batch.assessment} are in the gradebook, and `
        + "your students can see their feedback. When something needs your decision, it will be "
        + "waiting here."
      : `${examCount(batch.received)} from ${batch.assessment} were sent. `
        + `${examCount(batch.still_grading)} are still being graded; nothing needs your decision yet.`;
  const band = batch ? valueBand(batch) : pitchLine();
  host.className = "screen";
  host.append(
    el("p", { class: "eyebrow", text: batch ? batch.assessment : "Your class" }),
    el("h1", { class: "display", text: "Nothing needs you." }),
    el("p", {
      class: "lede",
      text: lede,
    }),
    ...(band ? [band] : []),
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
      text: when
        ? `Last sent ${when} — ${examCount(batch.received)}, ${batch.assessment}.`
        : `Most recent batch — ${examCount(batch.received)}, ${batch.assessment}.`,
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

function reviewHistory(ctx) {
  const history = ctx.summary.history || [];
  if (!history.length) {
    return null;
  }
  return el("section", { class: "panel review-history" }, [
    el("h2", { text: "Decisions in this batch" }),
    el("p", { text: "Open any exam again to check the scan and the decision already recorded." }),
    el("ul", { class: "group-list" }, history.map((item) => el("li", {}, [
      el("button", {
        class: "held-open",
        type: "button",
        onclick: () => ctx.goReview("history", item.review_id),
      }, [
        el("span", { class: "group-student", text: item.student_name }),
        el("span", {
          class: "group-reason",
          text: decisionStatus(item.status),
        }),
      ]),
    ]))),
  ]);
}

function decisionStatus(status) {
  if (status === "overridden") return "Marks changed by you";
  if (status === "dismissed") return "Returned to you for manual grading";
  if (status === "resolved") return "Resolved automatically";
  return "Approved by you";
}

function examOrder(ctx) {
  const batch = ctx.batch;
  const files = batch && batch.files ? batch.files : [];
  if (!files.length) {
    return null;
  }
  const waiting = ctx.summary.waiting || [];
  const history = ctx.summary.history || [];
  return el("section", { class: "panel exam-order" }, [
    el("h2", { text: "Exams in the order you sent them" }),
    el("ol", { class: "exam-order-list" }, files.map((file) => {
      const studentId = fileStem(file);
      const pending = waiting.find((item) => item.job_id === batch.job_id
        && item.student_id === studentId);
      const decided = history.find((item) => item.student_id === studentId);
      const record = (ctx.batchRecords || []).find((item) => item.job_id === batch.job_id
        && item.student_id === studentId);
      const status = pending
        ? "Waiting for you"
        : decided
          ? decisionStatus(decided.status)
          : record ? "In the gradebook" : batch.settled ? "Could not be graded" : "Still grading";
      const action = pending
        ? () => ctx.goReview(pending.group, pending.review_id)
        : decided
          ? () => ctx.goReview("history", decided.review_id)
          : record ? () => ctx.openGrade(studentId) : null;
      const content = [
        el("span", { class: "group-student", text: prettyName(studentId) }),
        el("span", { class: "group-reason", text: status }),
      ];
      return el("li", {}, action
        ? [el("button", { class: "held-open", type: "button", onclick: action }, content)]
        : content);
    })),
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
  const history = reviewHistory(ctx);
  const ordered = examOrder(ctx);
  if (ordered) {
    host.append(ordered);
  } else if (history) {
    host.append(history);
  }
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
  const history = reviewHistory(ctx);
  const ordered = examOrder(ctx);
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
    ...(!ordered && history ? [history] : []),
    ...(ordered ? [ordered] : []),
    el("div", { class: "button-row" }, [
      el("button", { class: "primary", type: "button", text: "See the grades", onclick: () => ctx.goGrades() }),
      el("button", { class: "secondary", type: "button", text: "Send more scans", onclick: () => ctx.goHome() }),
    ])
  );
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
    oninput: (event) => ctx.setGradeQuery(event.target.value),
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
  if (ctx.summary.batches.length) {
    host.append(el("section", { class: "recent-batches", "aria-label": "Recent batches" }, [
      el("h2", { text: "Recent batches" }),
      el("div", { class: "recent-batch-list" }, ctx.summary.batches.map((batch) =>
        el("button", {
          class: "recent-batch",
          type: "button",
          onclick: () => ctx.openBatch(batch.lot_code),
        }, [
          el("span", { class: "recent-batch-name", text: batch.assessment }),
          el("span", {
            class: "recent-batch-detail",
            text: `${examCount(batch.received)} · ${batch.settled ? "finished" : "in progress"}`,
          }),
        ]))),
    ]));
  }
  if (!ctx.records.length) {
    host.append(el("p", {
      class: "empty-line",
      text: query
        ? `No grade in the full history matches “${ctx.queries.grades.trim()}”.`
        : "No grades are in the gradebook yet. They appear here the moment grading finishes.",
    }));
    return;
  }
  const openId = openGradeId(ctx.queries);
  host.append(el("ul", { class: "grades" }, found.map((record) =>
    gradeRow(record, openId, (next) => ctx.setQuery(openGradeKey(), next)))));
  host.append(el("p", {
    class: "grades-foot",
    text: query
      ? `${found.length} matching ${plural(found.length, "grade", "grades")} shown from the full history.`
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
