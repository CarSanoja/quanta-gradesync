const IDS = {
  rail: "rail",
  modeChip: "mode-chip",
  queueChip: "queue-chip",
  refresh: "refresh-button",
  tokenButton: "token-button",
  gate: "token-gate",
  tokenForm: "token-form",
  tokenInput: "token-input",
  tokenCancel: "token-cancel",
  tokenError: "token-error",
  toast: "toast",
  jobsList: "jobs-list",
  jobsCount: "jobs-count",
  jobDetail: "job-detail",
  reviewList: "review-list",
  reviewCount: "review-count",
  reviewDetail: "review-detail",
  reviewBulkButton: "review-bulk-button",
  optimizerVariants: "optimizer-variants",
  optimizerCycles: "optimizer-cycles",
  cyclesCount: "cycles-count",
  fleetSummary: "fleet-summary",
  fleetAgents: "fleet-agents",
  fleetCount: "fleet-count",
  sisRecords: "sis-records",
  sisCount: "sis-count",
  sisPoll: "sis-poll",
  liveJobs: "live-jobs",
  liveStageTrack: "live-stage-track",
  liveElapsed: "live-elapsed",
  liveCalls: "live-calls",
  liveTokens: "live-tokens",
  liveEventsCount: "live-events-count",
  livePoll: "live-poll",
  liveStatusText: "live-status-text",
  liveTraceLink: "live-trace-link",
  liveExport: "live-export",
  liveTabs: "live-tabs",
  liveBoard: "live-board",
  liveTicker: "live-ticker",
  liveDetail: "live-detail",
  liveChain: "live-chain",
  livePostrun: "live-postrun",
  lotCodeInput: "lot-code-input",
  dropzone: "dropzone",
  fileInput: "file-input",
  sampleBatchButton: "sample-batch-button",
  uploadList: "upload-list",
  uploadCount: "upload-count",
  collisionGate: "collision-gate",
  collisionMessage: "collision-message",
  collisionRenameInput: "collision-rename-input",
  collisionError: "collision-error",
  collisionCancel: "collision-cancel",
  collisionReplace: "collision-replace",
  collisionRename: "collision-rename",
};

const TOAST_MS = 4000;
const REJECTED = "The API rejected that token. Paste the deployment token to continue.";

export function resolveDom() {
  const map = {};
  Object.entries(IDS).forEach(([key, id]) => {
    map[key] = document.getElementById(id);
  });
  return map;
}

export function createChrome(dom, { ApiError, getToken, setToken, onToken }) {
  let timer = null;

  function toast(message, tone) {
    dom.toast.textContent = message;
    dom.toast.dataset.tone = tone || "neutral";
    dom.toast.hidden = false;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      dom.toast.hidden = true;
    }, TOAST_MS);
  }

  function openGate(message) {
    dom.tokenError.textContent = message || "";
    dom.tokenError.hidden = !message;
    dom.tokenInput.value = getToken();
    dom.gate.hidden = false;
    dom.tokenInput.focus();
  }

  async function guard(action) {
    try {
      return await action();
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        openGate(REJECTED);
        return null;
      }
      toast(error.message, "danger");
      return null;
    }
  }

  dom.tokenButton.addEventListener("click", () => openGate(""));
  dom.tokenCancel.addEventListener("click", () => {
    dom.gate.hidden = true;
  });
  dom.tokenForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = dom.tokenInput.value.trim();
    if (!value) {
      dom.tokenError.textContent = "A bearer token is required.";
      dom.tokenError.hidden = false;
      return;
    }
    setToken(value);
    dom.gate.hidden = true;
    await onToken();
  });

  return { toast, openGate, guard, onAuthError: () => openGate(REJECTED) };
}
