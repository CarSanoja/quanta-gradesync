import { el } from "/console/assets/render.js";

const MINUTES_PER_EXAM = 5;

export function markingTime(exams) {
  const minutes = Math.max(0, exams) * MINUTES_PER_EXAM;
  if (minutes < 60) {
    return `${minutes} minutes`;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} hours ${rest} minutes` : `${hours} hours`;
}

export function valueBand(batch) {
  if (!batch) {
    return null;
  }
  const graded = Number(batch.graded_automatically) || 0;
  const received = Number(batch.received) || 0;
  if (graded < 1 || received < 1) {
    return null;
  }
  return el("aside", { class: "value-band" }, [
    el("strong", { text: `${graded} of ${received} were graded without you.` }),
    el("span", {
      text: `That is about ${markingTime(graded)} of marking you did not do,`
        + " counting five minutes an exam.",
    }),
  ]);
}

export function pitchLine() {
  return el("aside", { class: "value-band is-quiet" }, [
    el("strong", { text: "Marking costs about five minutes an exam." }),
    el("span", {
      text: "A hundred students and two hundred exams a month is eighteen hours,"
        + " every month. Send the scans: what can be graded is graded, and only"
        + " what genuinely needs you waits here.",
    }),
  ]);
}
