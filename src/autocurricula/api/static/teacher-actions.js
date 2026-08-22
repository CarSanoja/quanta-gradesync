import { ApiError, endpoints, getJson, postJson } from "/console/assets/api.js";
import {
  askConfirm, closeConfirm, confirmBusy, confirmError, openGate, showAlert, toast,
} from "/teacher/assets/teacher-dialogs.js";
import { examCount, plural, prettyName } from "/teacher/assets/teacher-format.js";
import { activeBatch, currentReview, followJob, state } from "/teacher/assets/teacher-state.js";

const SUMMARY_PATH = "/teacher/summary";
const BATCH_RECORD_LIMIT = 200;

let refresh = null;

export async function guard(action) {
  try {
    return await action();
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      openGate("That access code didn't work. Check it and try again.");
      return null;
    }
    toast(error.message);
    return null;
  }
}

export async function loadSummary() {
  const path = state.lotCode
    ? `${SUMMARY_PATH}?batch=${encodeURIComponent(state.lotCode)}`
    : SUMMARY_PATH;
  const summary = await guard(() => getJson(path));
  if (!summary) {
    state.failed = true;
    showAlert("Your page could not be loaded just now.");
    return;
  }
  state.failed = false;
  showAlert("");
  state.summary = summary;
}

export async function loadRecords() {
  const payload = await guard(() => getJson(endpoints.sisRecords()));
  if (payload) {
    state.records = payload.items;
  }
}

export async function loadBatchRecords() {
  const batch = activeBatch();
  if (!batch) {
    state.batchRecords = [];
    return;
  }
  const payload = await guard(() =>
    getJson(endpoints.sisRecords(batch.job_id, BATCH_RECORD_LIMIT)));
  state.batchRecords = payload ? payload.items : [];
}

function overridePayload(review) {
  const marks = state.review.marks || {};
  return {
    scores: review.criteria.map((criterion) => ({
      criterion_id: criterion.criterion_id,
      score: marks[criterion.criterion_id] === undefined
        ? criterion.score
        : marks[criterion.criterion_id],
    })),
  };
}

function decisionCall(review, action, corrected) {
  if (action === "dismiss") {
    return postJson(endpoints.dismiss(review.review_id));
  }
  if (corrected) {
    return postJson(
      `/review/${encodeURIComponent(review.review_id)}/override`, overridePayload(review));
  }
  return postJson(endpoints.approve(review.review_id));
}

export async function decide(action, buttons) {
  const review = currentReview();
  if (!review) {
    return;
  }
  const corrected = action === "accept" && state.review.editing && review.criteria.length > 0;
  buttons.forEach((button) => { button.disabled = true; });
  const done = await guard(() => decisionCall(review, action, corrected));
  buttons.forEach((button) => { button.disabled = false; });
  if (!done) {
    return;
  }
  toast(action === "dismiss"
    ? `${review.student_name}'s exam came back to you — no grade was recorded.`
    : `${review.student_name}'s grade is in the gradebook.`);
  Object.assign(state.review, { editing: false, marks: null, painted: "" });
  followJob(review.job_id);
  await refresh();
}

function refusalNote(error) {
  const refused = error.body && Array.isArray(error.body.refused) ? error.body.refused : [];
  if (!refused.length) {
    return error.message;
  }
  const names = refused.map((entry) => prettyName(entry.student_id || entry.review_id));
  return `Nothing was put in the gradebook. ${names.join(", ")} need your judgement — `
    + "review those one at a time.";
}

async function releaseHeld() {
  const held = state.summary.batch_hold;
  const ids = held.items.map((item) => item.review_id);
  if (!ids.length) {
    closeConfirm();
    return;
  }
  confirmBusy(true);
  try {
    const result = await postJson(endpoints.bulkApprove(), { review_ids: ids });
    closeConfirm();
    const failed = (result.failed || []).length;
    const done = `${examCount(result.released_count)} `
      + `${plural(result.released_count, "is", "are")} in the gradebook.`;
    toast(failed
      ? `${done} ${failed} could not be written and are still waiting — try again.`
      : done);
    followJob(held.items[0].job_id);
    await refresh();
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      closeConfirm();
      openGate("That access code didn't work. Check it and try again.");
    } else {
      confirmError(error instanceof ApiError ? refusalNote(error) : error.message);
    }
  } finally {
    confirmBusy(false);
  }
}

export function askRelease() {
  const held = state.summary.batch_hold;
  const judged = state.summary.judgement.count;
  askConfirm({
    title: `Put ${examCount(held.count)} in the gradebook?`,
    body: `These ${held.count} grades go into the gradebook exactly as proposed, and those `
      + "students can see their feedback.",
    aside: judged
      ? `The ${examCount(judged)} that need your judgement stay here until you look at them.`
      : "",
    yes: `Yes, put all ${held.count} in`,
    onYes: releaseHeld,
  });
}

export function setupActions(options) {
  refresh = options.refresh;
}
