import { progressFor, progressLabel } from "/console/assets/console-job-progress.js";
import {
  clear,
  el,
  emptyState,
  formatDateTime,
  formatPercent,
  metaRow,
  metric,
  pill,
  table,
} from "./render.js";
import { criteriaTable } from "./views-criteria.js";

const IN_THE_SIS = new Set(["synced", "approved"]);
const expanded = new Set();
let expandedJobId = null;

function navigate(name, argument) {
  const go = window[name];
  if (typeof go === "function") {
    go(argument);
  }
}

export function renderJobsList(target, jobs, activeId, onSelect) {
  clear(target);
  if (!jobs.length) {
    target.append(
      emptyState(
        "No batches yet",
        "Open Ingest and drop exam scans into a lot - the finished upload starts the pipeline by itself."
      )
    );
    return;
  }
  const list = el("div", { class: "list" });
  jobs.forEach((job) => {
    list.append(
      el(
        "button",
        {
          type: "button",
          class: `list-item${job.job_id === activeId ? " is-active" : ""}`,
          onclick: () => onSelect(job.job_id),
        },
        [
          el("span", { class: "list-title" }, [
            el("span", { class: "mono", text: job.job_id }),
            pill(job.stage, job.stage === "completed" ? "succeeded" : job.stage),
          ]),
          metaRow([`${job.subject} · ${job.class_id}`, `updated ${formatDateTime(job.updated_at)}`]),
          el(
            "span",
            { class: "stage-track" },
            job.stages.map((stage) => pill(stage.name, stage.status))
          ),
        ]
      )
    );
  });
  target.append(list);
}

function countStatus(students, predicate) {
  return String(students.filter(predicate).length);
}

function jobTiles(detail) {
  const rows = detail.students;
  const withStatus = (name) => countStatus(rows, (student) => student.sis_status === name);
  return el("dl", { class: "metrics" }, [
    metric("Submissions", String(detail.submission_count)),
    metric("Graded", String(detail.graded_count)),
    metric("In the SIS", countStatus(rows, (student) => IN_THE_SIS.has(student.sis_status))),
    metric("Held for review", withStatus("quarantined")),
    metric("Dismissed", withStatus("dismissed")),
    metric("Write failed", withStatus("failed")),
  ]);
}

function statusCell(student, progress) {
  // Only a row the checkpoint still calls pending can be told apart by the
  // feed. Anything already decided keeps the decided word.
  const live = student.sis_status === "pending" ? progressFor(progress, student) : null;
  if (!live) {
    return pill(student.sis_status, student.sis_status);
  }
  return pill(progressLabel(live), "running");
}

function studentRow(student, onOpenReview, onToggle, progress) {
  const open = expanded.has(student.student_id);
  return el("tr", {}, [
    el("td", {}, el("span", { class: "mono", text: student.student_id })),
    el("td", { class: "numeric", text: formatPercent(student.percentage) }),
    el("td", {}, statusCell(student, progress)),
    el(
      "td",
      {},
      el("div", { class: "row-actions" }, [
        student.sis_status === "quarantined"
          ? el("button", {
              class: "ghost",
              type: "button",
              text: "Review",
              onclick: () => onOpenReview(student.review_id),
            })
          : null,
        el("button", {
          class: "ghost",
          type: "button",
          text: open ? "Hide" : "Criteria",
          onclick: () => onToggle(student.student_id),
        }),
      ])
    ),
  ]);
}

function criteriaRow(student) {
  const body = student.criteria.length
    ? criteriaTable(student.criteria)
    : emptyState("No criterion detail", "The checkpoint no longer holds the grading result.");
  return el("tr", { class: "row-expanded" }, el("td", { colspan: "4" }, body));
}

function paintStudents(host, detail, onOpenReview, progress) {
  const toggle = (studentId) => {
    if (expanded.has(studentId)) {
      expanded.delete(studentId);
    } else {
      expanded.add(studentId);
    }
    paintStudents(host, detail, onOpenReview, progress);
  };
  const rows = [];
  detail.students.forEach((student) => {
    rows.push(studentRow(student, onOpenReview, toggle, progress));
    if (expanded.has(student.student_id)) {
      rows.push(criteriaRow(student));
    }
  });
  clear(host).append(
    table(
      [{ label: "Student" }, { label: "Score", numeric: true }, { label: "SIS" }, { label: "Action" }],
      rows
    )
  );
}

export function renderJobDetail(target, detail, onOpenReview, progress) {
  clear(target);
  if (!detail) {
    target.append(emptyState("Select a batch", "Stage checkpoints appear here."));
    return;
  }
  const job = detail.job;
  if (expandedJobId !== job.job_id) {
    expanded.clear();
    expandedJobId = job.job_id;
  }
  target.append(jobTiles(detail));
  target.append(
    metaRow([
      el("span", { class: "mono", text: `gs://${job.bucket}/${job.exam_batch_prefix}` }),
      `trace ${job.trace_id}`,
      `triggered ${formatDateTime(job.triggered_at)}`,
    ])
  );
  target.append(
    el("div", { class: "actions is-inline" }, [
      el("button", {
        class: "ghost",
        type: "button",
        text: "Open in Mission control",
        onclick: () => navigate("goToMissionControl", { jobId: job.job_id }),
      }),
      el("button", {
        class: "ghost",
        type: "button",
        text: "Grades in the SIS ledger",
        onclick: () => navigate("goToSisLedger", job.job_id),
      }),
    ])
  );
  if (job.error) {
    target.append(el("p", { class: "section-title", text: "Failure" }));
    target.append(el("ul", { class: "reasons" }, el("li", { class: "reason", text: job.error })));
  }
  target.append(el("p", { class: "section-title", text: "Pipeline stages" }));
  target.append(
    el(
      "div",
      { class: "stage-track" },
      job.stages.map((stage) => pill(`${stage.name} · ${stage.status}`, stage.status))
    )
  );
  target.append(el("p", { class: "section-title", text: "Students" }));
  if (!detail.students.length) {
    target.append(emptyState("No submissions recorded", "The fetch stage has not completed."));
    return;
  }
  const host = el("div", { class: "student-table" });
  target.append(host);
  paintStudents(host, detail, onOpenReview, progress);
}
