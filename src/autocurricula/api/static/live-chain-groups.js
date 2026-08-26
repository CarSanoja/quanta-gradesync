import { classifyEvent } from "./live-kinds.js";

const GRADING_PREFIX = "Grading_";
const OPEN_SEQ = Number.MAX_SAFE_INTEGER;

export function directStudent(event) {
  if (event.student_id) {
    return event.student_id;
  }
  const attributes = event.attributes || {};
  if (typeof attributes.student_id === "string" && attributes.student_id) {
    return attributes.student_id;
  }
  const name = event.name || "";
  if (name.startsWith(GRADING_PREFIX)) {
    return name.slice(GRADING_PREFIX.length) || null;
  }
  return null;
}

function buildIndex(events) {
  const spanStudent = new Map();
  const parents = new Map();
  const windows = [];
  const open = new Map();
  events.forEach((event) => {
    const student = directStudent(event);
    if (event.span_id) {
      if (student && !spanStudent.has(event.span_id)) {
        spanStudent.set(event.span_id, student);
      }
      if (event.parent_span_id) {
        parents.set(event.span_id, event.parent_span_id);
      }
    }
    if (!student || classifyEvent(event) !== "grading") {
      return;
    }
    if (event.kind === "span_start") {
      const window = { student, start: event.seq, end: OPEN_SEQ };
      windows.push(window);
      open.set(student, window);
    } else if (event.kind === "span_end" && open.has(student)) {
      open.get(student).end = event.seq;
      open.delete(student);
    }
  });
  return { spanStudent, parents, windows };
}

function studentOf(event, index) {
  const direct = directStudent(event);
  if (direct) {
    return direct;
  }
  let spanId = event.span_id || event.parent_span_id;
  const seen = new Set();
  while (spanId && !seen.has(spanId)) {
    seen.add(spanId);
    const found = index.spanStudent.get(spanId);
    if (found) {
      return found;
    }
    spanId = index.parents.get(spanId);
  }
  const window = index.windows.find(
    (item) => event.seq >= item.start && event.seq <= item.end
  );
  return window ? window.student : null;
}

export function groupByStudent(events) {
  const ordered = (events || []).slice().sort((left, right) => left.seq - right.seq);
  const index = buildIndex(ordered);
  const groups = new Map();
  ordered.forEach((event) => {
    const student = studentOf(event, index);
    if (!student) {
      return;
    }
    if (!groups.has(student)) {
      groups.set(student, []);
    }
    groups.get(student).push(event);
  });
  return groups;
}
