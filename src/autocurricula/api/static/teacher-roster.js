import { fileStem } from "/teacher/assets/teacher-filenames.js";
import { fmt, prettyName } from "/teacher/assets/teacher-format.js";

export const BANDS = [
  {
    key: "judgement",
    title: "Waiting for your judgement",
    tone: "is-waiting-tone",
    chip: "Waiting for you",
    note: "Something on these pages will not be decided without you. You see them one at a time.",
  },
  {
    key: "batch_hold",
    title: "Held as a precaution",
    tone: "is-held-tone",
    chip: "Held as a precaution",
    note: "Nothing was found wrong with these. They stopped only because they arrived in the same "
      + "batch as something else.",
  },
  {
    key: "failed",
    title: "Could not be graded",
    tone: "is-failed-tone",
    chip: "Could not be graded",
    note: "Nothing was read from these pages, so nothing was written to the gradebook. Send those "
      + "scans again and the rest of the batch is untouched.",
  },
  {
    key: "grading",
    title: "Still being graded",
    tone: "is-quiet-tone",
    chip: "Still being graded",
    note: "Nothing is asked of you while these run. You can close the page.",
  },
  {
    key: "gradebook",
    title: "In the gradebook",
    tone: "is-done-tone",
    chip: "In the gradebook",
    note: "Graded without you, and your students can see their feedback.",
  },
  {
    key: "decided",
    title: "Decided by you",
    tone: "is-sent-tone",
    chip: "Decided by you",
    note: "You looked at these yourself. The decision is recorded next to each one.",
  },
];

export function decisionStatus(status) {
  if (status === "overridden") return "Marks changed by you";
  if (status === "dismissed") return "Returned to you for manual grading";
  if (status === "resolved") return "Resolved automatically";
  return "Approved by you";
}

function scoreText(record) {
  if (!record || record.total_score === null || record.total_score === undefined) {
    return "";
  }
  const max = record.percentage ? (100 * record.total_score) / record.percentage : null;
  return `${fmt(record.total_score)}${max ? ` of ${fmt(max)}` : ""}`;
}

function place(batch, studentId, ctx) {
  const waiting = (ctx.summary.waiting || []).find((item) => item.job_id === batch.job_id
    && item.student_id === studentId);
  if (waiting) {
    return { key: waiting.group === "batch_hold" ? "batch_hold" : "judgement", item: waiting };
  }
  const decided = (ctx.summary.history || []).find((item) => item.student_id === studentId);
  if (decided) {
    return { key: "decided", item: decided };
  }
  const record = (ctx.batchRecords || []).find((item) => item.job_id === batch.job_id
    && item.student_id === studentId);
  if (record) {
    return { key: "gradebook", record };
  }
  return { key: batch.settled ? "failed" : "grading" };
}

export function buildRoster(ctx) {
  const batch = ctx.batch;
  const files = batch && batch.files ? batch.files : [];
  return files.map((file, index) => {
    const studentId = fileStem(file);
    const spot = place(batch, studentId, ctx);
    const band = BANDS.find((entry) => entry.key === spot.key);
    return {
      position: String(index + 1).padStart(2, "0"),
      studentId,
      student: prettyName(studentId),
      file,
      band: spot.key,
      chip: spot.key === "decided" ? decisionStatus(spot.item.status) : band.chip,
      tone: band.tone,
      reason: spot.item && spot.item.primary_reason ? spot.item.primary_reason : "",
      score: scoreText(spot.record),
      open: spot.item
        ? () => ctx.goReview(spot.key === "decided" ? "history" : spot.item.group, spot.item.review_id)
        : spot.record ? () => ctx.openGrade(studentId) : null,
    };
  });
}

export function countBand(roster, key) {
  return roster.filter((row) => row.band === key).length;
}
