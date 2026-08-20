import { clear, el, emptyState, pill } from "./render.js";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const MAX_FILES_PER_DROP = 40;
const ALLOWED_SUFFIXES = new Set([".jpg", ".jpeg", ".png", ".pdf", ".heic"]);
const LOT_CODE_RE = /^\d{4}_[A-Za-z0-9-]+_[A-Za-z0-9-]+_[A-Za-z0-9-]+$/;

const PILL_STATES = {
  stored: "succeeded", replaced: "succeeded", renamed: "succeeded",
  uploading: "running", collision: "quarantined", queued: "pending",
  skipped: "pending", failed: "failed",
};

function suffixOf(name) {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

function uploadRow(item) {
  return el("div", { class: "upload-row" }, [
    el("div", { class: "upload-name" }, [
      el("span", { class: "mono", text: item.label }),
      el("span", { class: "upload-note", text: item.note || "" }),
    ]),
    pill(item.status, PILL_STATES[item.status] || "pending"),
  ]);
}

export function renderUploads(target, counter, uploads) {
  clear(target);
  const done = uploads.filter((item) => PILL_STATES[item.status] === "succeeded").length;
  counter.textContent = uploads.length ? `${done}/${uploads.length} stored` : "";
  if (!uploads.length) {
    target.append(emptyState("Nothing uploaded yet", "Dropped scans and their outcomes appear here."));
    return;
  }
  uploads.slice().reverse().forEach((item) => target.append(uploadRow(item)));
}

export function createIngestController({ dom, toast, postForm, postJson, endpoints, onAuthError, guard }) {
  const uploads = [];
  let dialogResolver = null;

  function paint() {
    renderUploads(dom.uploadList, dom.uploadCount, uploads);
  }

  function askCollision(fileName) {
    dom.collisionMessage.textContent =
      `A scan named ${fileName} already exists in this batch. The file stem is the student id: ` +
      "replace that student's scan, or store this file under a different student.";
    dom.collisionRenameInput.hidden = true;
    dom.collisionRenameInput.value = "";
    dom.collisionError.hidden = true;
    dom.collisionGate.hidden = false;
    return new Promise((resolve) => {
      dialogResolver = resolve;
    });
  }

  function settleDialog(result) {
    if (dialogResolver) {
      dom.collisionGate.hidden = true;
      dialogResolver(result);
      dialogResolver = null;
    }
  }

  dom.collisionCancel.addEventListener("click", () => settleDialog({ action: "cancel" }));
  dom.collisionReplace.addEventListener("click", () => settleDialog({ action: "replace" }));
  dom.collisionRename.addEventListener("click", () => {
    if (dom.collisionRenameInput.hidden) {
      dom.collisionRenameInput.hidden = false;
      dom.collisionRenameInput.focus();
      return;
    }
    const name = dom.collisionRenameInput.value.trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name)) {
      dom.collisionError.textContent = "Student id: letters, digits, dot, dash or underscore.";
      dom.collisionError.hidden = false;
      return;
    }
    settleDialog({ action: "rename", name });
  });

  async function send(file, lotCode, mode, newName) {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("lot_code", lotCode);
    form.append("mode", mode);
    if (newName) {
      form.append("new_student_name", newName);
    }
    return postForm(endpoints.ingestExam(), form);
  }

  async function uploadOne(item, file, lotCode) {
    item.status = "uploading";
    paint();
    let mode = "new";
    let newName = "";
    for (;;) {
      const result = await send(file, lotCode, mode, newName);
      if (result.status === 401 || result.status === 403) {
        item.status = "failed";
        item.note = "token rejected; set the session token and retry";
        onAuthError();
        return;
      }
      if (result.ok) {
        item.status = mode === "new" ? "stored" : mode === "replace" ? "replaced" : "renamed";
        item.note = result.body ? result.body.object : "";
        return;
      }
      if (result.status === 409 && result.body && result.body.collision) {
        item.status = "collision";
        paint();
        const decision = await askCollision(file.name);
        if (decision.action === "cancel") {
          item.status = "skipped";
          item.note = "kept the existing scan";
          return;
        }
        mode = decision.action;
        newName = decision.name || "";
        item.status = "uploading";
        paint();
        continue;
      }
      item.status = "failed";
      item.note = result.body && result.body.detail ? String(result.body.detail) : `HTTP ${result.status}`;
      return;
    }
  }

  async function handleFiles(fileList) {
    const lotCode = dom.lotCodeInput.value.trim();
    if (!LOT_CODE_RE.test(lotCode)) {
      toast("Lot code must follow {year}_{subject}_{class}_{assessment}.", "danger");
      dom.lotCodeInput.focus();
      return;
    }
    const files = Array.from(fileList).slice(0, MAX_FILES_PER_DROP);
    if (fileList.length > MAX_FILES_PER_DROP) {
      toast(`Only the first ${MAX_FILES_PER_DROP} files were taken.`, "danger");
    }
    for (const file of files) {
      const item = { label: file.name, status: "queued", note: "" };
      uploads.push(item);
      if (!ALLOWED_SUFFIXES.has(suffixOf(file.name))) {
        item.status = "failed";
        item.note = "not a gradable type (jpg, jpeg, png, pdf, heic)";
        continue;
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        item.status = "failed";
        item.note = "over the 20 MB limit";
        continue;
      }
      paint();
      await uploadOne(item, file, lotCode);
      paint();
    }
    paint();
  }

  dom.dropzone.addEventListener("click", () => dom.fileInput.click());
  dom.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      dom.fileInput.click();
    }
  });
  dom.fileInput.addEventListener("change", () => {
    if (dom.fileInput.files.length) {
      handleFiles(dom.fileInput.files);
      dom.fileInput.value = "";
    }
  });
  ["dragenter", "dragover"].forEach((name) =>
    dom.dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dom.dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((name) =>
    dom.dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dom.dropzone.classList.remove("is-dragover");
    })
  );
  dom.dropzone.addEventListener("drop", (event) => {
    if (event.dataTransfer && event.dataTransfer.files.length) {
      handleFiles(event.dataTransfer.files);
    }
  });

  dom.sampleBatchButton.addEventListener("click", async () => {
    dom.sampleBatchButton.disabled = true;
    const payload = await guard(() => postJson(endpoints.sampleBatch()));
    dom.sampleBatchButton.disabled = false;
    if (!payload) {
      return;
    }
    uploads.push({
      label: payload.destination_prefix,
      status: "stored",
      note: `${payload.count} objects copied · job ${payload.expected_job_id}`,
    });
    paint();
    toast(`Sample batch loaded. Watch job ${payload.expected_job_id} in Live trace.`, "neutral");
  });

  paint();
  return { paint };
}
