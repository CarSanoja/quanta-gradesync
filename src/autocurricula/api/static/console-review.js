import { ApiError } from "./api.js";
import { renderQueueCleared, renderReviewDetail, renderReviewList } from "./views.js";

const EMPTY_CONTEXT = { item: null, criteria: [], imageUrl: null };

function refusalNote(error) {
  const body = error && error.body;
  const refused = body && Array.isArray(body.refused) ? body.refused : [];
  if (!refused.length) {
    return error.message;
  }
  const names = refused.map((entry) => entry.student_id || entry.review_id);
  return `Nothing was released. ${names.join(", ")} need your judgement - review those one at a time.`;
}

export function createReviewController(deps) {
  const { dom, guard, getJson, postJson, endpoints, toast, setView } = deps;
  const { getObjectUrl, jobDetailFor, onDecided } = deps;
  const state = { items: [], activeId: null, context: { ...EMPTY_CONTEXT }, lastJobId: null, held: [] };

  function releaseImage() {
    if (state.context.imageUrl) {
      URL.revokeObjectURL(state.context.imageUrl);
    }
    state.context.imageUrl = null;
  }

  function paintDetail() {
    if (state.context.item || state.items.length) {
      renderReviewDetail(dom.reviewDetail, state.context, handlers);
      return;
    }
    renderQueueCleared(dom.reviewDetail, state.lastJobId);
  }

  async function loadImage(item, reviewId) {
    if (!item.document_paths.length) {
      return;
    }
    try {
      state.context.imageUrl = await getObjectUrl(endpoints.pageImage(reviewId, 0));
    } catch (error) {
      state.context.imageUrl = null;
    }
  }

  async function select(reviewId) {
    const item = state.items.find((candidate) => candidate.review_id === reviewId) || null;
    releaseImage();
    state.activeId = reviewId;
    state.context = { item, criteria: [], imageUrl: null };
    renderReviewList(dom.reviewList, state.items, state.activeId, select);
    paintDetail();
    if (!item) {
      return;
    }
    const detail = await jobDetailFor(item.job_id);
    const student = detail
      ? detail.students.find((candidate) => candidate.student_id === item.student_id)
      : null;
    state.context.criteria = student ? student.criteria : [];
    await loadImage(item, reviewId);
    if (state.activeId === reviewId) {
      paintDetail();
    }
  }

  function paintBulkButton() {
    const button = dom.reviewBulkButton;
    if (!button) {
      return;
    }
    const count = state.held.length;
    button.hidden = count === 0;
    button.textContent = `Release ${count} held only by the batch rule`;
  }

  async function loadHeld() {
    const summary = await guard(() => getJson(endpoints.teacherSummary()));
    const group = summary && summary.batch_hold ? summary.batch_hold : null;
    state.held = group && group.count > 0 && Array.isArray(group.items) ? group.items : [];
    paintBulkButton();
  }

  async function load() {
    const payload = await guard(() => getJson(endpoints.pending()));
    if (!payload) {
      return;
    }
    state.items = payload.items;
    dom.reviewCount.textContent = `${payload.count} item${payload.count === 1 ? "" : "s"}`;
    dom.queueChip.textContent = `queue: ${payload.count} pending`;
    dom.queueChip.dataset.tone = payload.count ? "warn" : "ok";
    await loadHeld();
    const stillPending = state.items.some((item) => item.review_id === state.activeId);
    const nextId = stillPending
      ? state.activeId
      : state.items.length
        ? state.items[0].review_id
        : null;
    renderReviewList(dom.reviewList, state.items, nextId, select);
    if (nextId) {
      await select(nextId);
      return;
    }
    releaseImage();
    state.activeId = null;
    state.context = { ...EMPTY_CONTEXT };
    paintDetail();
  }

  async function decide(reviewId, endpoint, approved) {
    const item = state.items.find((candidate) => candidate.review_id === reviewId) || null;
    const decided = await guard(() => postJson(endpoint(reviewId)));
    if (!decided) {
      return;
    }
    if (approved) {
      state.lastJobId = item ? item.job_id : state.lastJobId;
      toast(`${decided.student_id} approved · written to the SIS ledger.`, "neutral");
    } else {
      toast(`${decided.student_id} dismissed without a SIS write.`, "neutral");
    }
    await onDecided();
    await load();
  }

  const handlers = {
    onApprove: (reviewId) => decide(reviewId, endpoints.approve, true),
    onDismiss: (reviewId) => decide(reviewId, endpoints.dismiss, false),
  };

  async function releaseHeld() {
    const items = state.held;
    if (!items.length) {
      return;
    }
    const question = `Release ${items.length} exam(s) held only by the batch rule into the SIS?`;
    if (!window.confirm(question)) {
      return;
    }
    const released = await guard(async () => {
      try {
        return await postJson(endpoints.bulkApprove(), {
          review_ids: items.map((item) => item.review_id),
        });
      } catch (error) {
        if (error instanceof ApiError && error.status === 409) {
          toast(refusalNote(error), "danger");
          return null;
        }
        throw error;
      }
    });
    if (!released) {
      return;
    }
    state.lastJobId = items[0].job_id || state.lastJobId;
    toast(`${released.released_count} grade(s) written to the SIS ledger.`, "neutral");
    await onDecided();
    await load();
  }

  async function openFromJob(reviewId) {
    setView("review");
    if (!state.items.some((item) => item.review_id === reviewId)) {
      await load();
    }
    if (state.items.some((item) => item.review_id === reviewId)) {
      await select(reviewId);
      return;
    }
    toast("That record is no longer pending review.", "neutral");
  }

  if (dom.reviewBulkButton) {
    dom.reviewBulkButton.hidden = true;
    dom.reviewBulkButton.addEventListener("click", releaseHeld);
  }

  return { load, select, openFromJob };
}
