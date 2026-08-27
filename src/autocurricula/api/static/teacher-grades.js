import { el } from "/console/assets/render.js";
import { fmt, prettyName, prettySubject, timeAgo } from "/teacher/assets/teacher-format.js";

const OPEN_KEY = "open_grade";

function criterionTitle(criterionId) {
  return prettyName(String(criterionId || "").replace(/[-_]+/g, " "));
}

function criterionRow(score) {
  const confidence = typeof score.confidence === "number"
    ? `read with ${Math.round(score.confidence * 100)}% confidence`
    : "";
  return el("li", { class: "criterion-row" }, [
    el("span", {
      class: "criterion-name",
      text: score.title || criterionTitle(score.criterion_id),
    }),
    el("span", { class: "criterion-score", text: fmt(score.score) }),
    confidence ? el("span", { class: "criterion-note", text: confidence }) : null,
  ]);
}

function breakdown(record) {
  const scores = record.criterion_scores || [];
  const nodes = [];
  if (scores.length) {
    nodes.push(el("p", { class: "criterion-head", text: "How this grade was made up" }));
    nodes.push(el("ul", { class: "criteria" }, scores.map(criterionRow)));
  }
  if (record.competency_codes && record.competency_codes.length) {
    nodes.push(el("p", {
      class: "criterion-note",
      text: `Curriculum codes: ${record.competency_codes.join(" · ")}`,
    }));
  }
  nodes.push(el("p", {
    class: "criterion-note",
    text: `Graded ${timeAgo(record.graded_at)}, written to the gradebook `
      + `${timeAgo(record.written_at)}.`,
  }));
  return el("div", { class: "grade-breakdown" }, nodes);
}

export function gradeRow(record, openId, onToggle) {
  const max = record.percentage ? (100 * record.total_score) / record.percentage : null;
  const detail = [prettySubject(record.subject), prettyName(record.term || "")]
    .filter(Boolean)
    .concat(`in the gradebook ${timeAgo(record.written_at)}`)
    .join(" · ");
  const score = record.total_score === null
    ? "graded"
    : `${fmt(record.total_score)}${max ? ` of ${fmt(max)}` : ""}`
      + `${record.percentage === null ? "" : ` · ${Math.round(record.percentage)}%`}`;
  const open = openId === record.student_id;
  const button = el("button", {
    type: "button",
    class: `grade-open${open ? " is-open" : ""}`,
    "aria-expanded": open ? "true" : "false",
    onclick: () => onToggle(open ? "" : record.student_id),
  }, [
    el("span", { class: "grade-who" }, [
      el("span", { class: "grade-student", text: prettyName(record.student_id) }),
      el("span", { class: "grade-detail", text: detail }),
    ]),
    el("span", { class: "grade-figure" }, [
      el("span", { class: "grade-score", text: score }),
      el("span", { class: "grade-more", text: open ? "Hide the detail" : "See the detail" }),
    ]),
  ]);
  return el("li", {}, [button, open ? breakdown(record) : null]);
}

export function openGradeId(queries) {
  return String((queries || {})[OPEN_KEY] || "");
}

export function openGradeKey() {
  return OPEN_KEY;
}
