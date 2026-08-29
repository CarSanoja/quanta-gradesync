import { endpoints, postForm } from "/console/assets/api.js";
import {
  ALLOWED_SUFFIXES, detectPageGroups, fileStem, fileSuffix, lotCodeFor, looksLikeCamera, slugify,
} from "/teacher/assets/teacher-filenames.js";
import { prettyName } from "/teacher/assets/teacher-format.js";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const RENAME_IDLE_MS = 900;

const SENT = new Set(["received", "skipped"]);
const FAILURE_COPY = [
  [/is empty/i, "this file has nothing in it"],
  [/exceeds the/i, "this file is too big"],
  [/not gradable/i, "not a photo or PDF"],
  [/already holds/i, "this assessment is full — start a new one"],
  [/reads as an instruction/i, "that name reads as an instruction to the grader"],
];
const NEEDS_NAME_DETAIL = /student id|student name|new_student_name/i;

export const uploads = {
  rows: [],
  // One entry per batch this teacher has sent in this sitting. rows is the queue
  // for whichever batch is moving right now and gets cleared between them, so
  // without this a finished section would vanish and she could not reach its
  // grades without leaving the page — which is the whole point of not leaving.
  batches: [],
  pair: null,
  lot: { subject: "", classId: "", assessment: "" },
  running: false,
  awaitingLot: false,
  lotCode: "",
  collisionForAll: null,
};

const UNRESOLVED = new Set(["failed", "needs-name", "held", "paused"]);

let hooks = {};
let renameTimer = null;
let nextRowId = 0;

function batchFor(lotCode) {
  const existing = uploads.batches.find((batch) => batch.lotCode === lotCode);
  if (existing) {
    return Object.assign(existing, { running: true, done: false });
  }
  const batch = { lotCode, total: 0, received: 0, skipped: 0, failed: 0, running: true, done: false };
  uploads.batches.push(batch);
  return batch;
}

function syncBatch(batch) {
  const counts = uploadState();
  Object.assign(batch, {
    total: counts.total,
    received: counts.received,
    skipped: counts.skipped,
    failed: counts.failed.length,
  });
}

export function lotCodeNow() {
  return lotCodeFor(uploads.lot);
}

export function uploadState() {
  const rows = uploads.rows;
  const sent = rows.filter((row) => SENT.has(row.state)).length;
  const received = rows.filter((row) => row.state === "received").length;
  const skipped = rows.filter((row) => row.state === "skipped").length;
  const sending = rows.filter((row) => row.state === "sending").length;
  const needsName = rows.filter((row) => row.state === "needs-name");
  const held = rows.filter((row) => row.state === "held");
  const failed = rows.filter((row) => row.state === "failed");
  return {
    total: rows.length,
    sent,
    received,
    skipped,
    sending,
    needsName,
    held,
    failed,
    running: uploads.running,
    awaitingLot: uploads.awaitingLot,
    finished: rows.length > 0 && sent === rows.length,
  };
}

function changed() {
  if (hooks.onChange) {
    hooks.onChange();
  }
}

function releaseThumb(row) {
  if (row.thumbUrl) {
    URL.revokeObjectURL(row.thumbUrl);
    row.thumbUrl = "";
  }
}

function failureCopy(detail) {
  const hit = FAILURE_COPY.find(([pattern]) => pattern.test(detail));
  return hit ? hit[1] : "we couldn't send this one";
}

function finish(row, state, status, note) {
  Object.assign(row, { state, status, note: note || "" });
  if (state !== "needs-name") {
    releaseThumb(row);
  }
}

export function renameRow(rowId, value) {
  const row = uploads.rows.find((entry) => entry.id === rowId);
  if (!row) {
    return;
  }
  row.name = value;
  row.studentId = slugify(value);
  row.student = row.studentId ? prettyName(row.studentId) : "";
  if (row.state === "needs-name" && row.studentId) {
    finish(row, "ready", "waiting to send");
  } else if (row.state === "ready" && !row.studentId) {
    finish(row, "needs-name", "needs a name");
  } else if (row.state === "failed" && row.studentId) {
    finish(row, "ready", "waiting to send");
  }
  changed();
  window.clearTimeout(renameTimer);
  renameTimer = window.setTimeout(() => runQueue(false), RENAME_IDLE_MS);
}

export function setLotField(key, value) {
  uploads.lot[key] = value;
  const waiting = uploads.awaitingLot && lotCodeNow();
  if (waiting) {
    uploads.awaitingLot = false;
  }
  changed();
  if (waiting) {
    runQueue(false);
  }
}

export function answerPair(action) {
  if (!uploads.pair) {
    return;
  }
  const names = new Set(uploads.pair.groups.flat());
  uploads.rows.filter((row) => row.state === "paused" && names.has(row.label))
    .forEach((row) => {
      if (action === "combine") {
        finish(row, "held", "held back",
          "Scan the pages into one PDF, pages in order, then send that single file.");
      } else {
        finish(row, "ready", "waiting to send");
      }
    });
  uploads.pair = null;
  changed();
  runQueue(false);
}

async function uploadRow(row, lotCode) {
  let mode = row.studentId === fileStem(row.label) ? "new" : "rename";
  let newName = mode === "rename" ? row.studentId : "";
  for (;;) {
    const form = new FormData();
    form.append("file", row.file, row.label);
    form.append("lot_code", lotCode);
    form.append("mode", mode);
    if (newName) {
      form.append("new_student_name", newName);
    }
    let result = null;
    try {
      result = await postForm(endpoints.ingestExam(), form);
    } catch (error) {
      finish(row, "failed", "we couldn't reach GradeSync");
      return true;
    }
    if (result.status === 401 || result.status === 403) {
      finish(row, "failed", "needs the access code");
      hooks.openGate("That access code didn't work. Check it and try again.");
      return false;
    }
    if (result.ok) {
      finish(row, "received", mode === "replace" ? "replaced" : "received");
      return true;
    }
    if (result.status === 409 && result.body && result.body.collision) {
      finish(row, "sending", "already has a scan");
      changed();
      const decision = uploads.collisionForAll
        || await hooks.askCollision(
          result.body.student_id || row.studentId,
          uploads.rows.indexOf(row) + 1,
          uploads.rows.length
        );
      if (decision.all && decision.action !== "rename") {
        uploads.collisionForAll = { action: decision.action, all: true };
      }
      if (decision.action === "cancel") {
        finish(row, "skipped", "kept the scan already saved");
        return true;
      }
      mode = decision.action;
      newName = decision.name || "";
      if (newName) {
        Object.assign(row, { studentId: newName, student: prettyName(newName), name: prettyName(newName) });
      }
      continue;
    }
    const detail = result.body && result.body.detail ? String(result.body.detail) : "";
    if (NEEDS_NAME_DETAIL.test(detail)) {
      finish(row, "needs-name", "needs a name", "GradeSync could not use that name — type the student's name.");
      return true;
    }
    finish(row, "failed", failureCopy(detail));
    return true;
  }
}

export async function runQueue(announce) {
  if (uploads.running || !uploads.rows.some((row) => row.state === "ready")) {
    return;
  }
  const lotCode = lotCodeNow();
  if (!lotCode) {
    uploads.awaitingLot = true;
    if (announce) {
      hooks.toast("Say which subject, class and assessment these scans belong to.");
    }
    changed();
    return;
  }
  uploads.awaitingLot = false;
  uploads.running = true;
  uploads.lotCode = lotCode;
  const batch = batchFor(lotCode);
  syncBatch(batch);
  changed();
  for (;;) {
    const row = uploads.rows.find((candidate) => candidate.state === "ready");
    if (!row) {
      break;
    }
    finish(row, "sending", "sending…");
    syncBatch(batch);
    changed();
    const carryOn = await uploadRow(row, lotCode);
    syncBatch(batch);
    changed();
    if (!carryOn) {
      break;
    }
  }
  uploads.running = false;
  const arrived = uploads.rows.some((row) => row.state === "received");
  syncBatch(batch);
  batch.running = false;
  batch.done = true;
  // Nothing left for her to answer means the queue has done its job, so it gets
  // out of the way and the next section can be dropped straight onto a clean
  // page. If something is unresolved the rows stay, because they are the only
  // place she can fix them.
  if (!uploads.rows.some((row) => UNRESOLVED.has(row.state))) {
    uploads.rows.forEach(releaseThumb);
    uploads.rows.length = 0;
    uploads.pair = null;
    uploads.collisionForAll = null;
  }
  changed();
  if (arrived) {
    hooks.onBatchSent(lotCode);
  }
}

export function retryFailed() {
  uploads.rows.filter((row) => row.state === "failed" && !row.local)
    .forEach((row) => finish(row, "ready", "waiting to send"));
  changed();
  runQueue(true);
}

export function resetUploads() {
  uploads.collisionForAll = null;
  uploads.rows.forEach(releaseThumb);
  uploads.rows.length = 0;
  uploads.pair = null;
  changed();
}

function stageFile(file, paused) {
  const stem = fileStem(file.name);
  const camera = looksLikeCamera(stem);
  const studentId = camera ? "" : slugify(stem);
  const row = {
    id: (nextRowId += 1),
    file,
    label: file.name,
    name: studentId ? prettyName(studentId) : "",
    studentId,
    student: studentId ? prettyName(studentId) : "",
    state: "ready",
    status: "waiting to send",
    note: "",
    thumbUrl: "",
  };
  if (!ALLOWED_SUFFIXES.has(fileSuffix(file.name))) {
    Object.assign(row, { state: "failed", status: "not a photo or PDF", local: true });
  } else if (file.size > MAX_UPLOAD_BYTES) {
    Object.assign(row, { state: "failed", status: "over the 20 MB limit", local: true });
  } else if (paused) {
    Object.assign(row, { state: "paused", status: "waiting on your answer" });
  } else if (camera) {
    Object.assign(row, { state: "needs-name", status: "needs a name" });
    if (file.type.startsWith("image/")) {
      row.thumbUrl = URL.createObjectURL(file);
    }
  }
  uploads.rows.push(row);
}

export function stageFiles(fileList) {
  const files = Array.from(fileList);
  if (!files.length) {
    return;
  }
  const state = uploadState();
  if (!uploads.running && ((state.finished && !state.failed.length) || !uploads.rows.length)) {
    resetUploads();
  }
  const candidates = files.filter((file) => !looksLikeCamera(fileStem(file.name)));
  const groups = detectPageGroups(candidates.map((file) => file.name));
  const paused = new Set(groups.flat());
  files.forEach((file) => stageFile(file, paused.has(file.name)));
  if (groups.length) {
    uploads.pair = { groups };
  }
  changed();
  runQueue(true);
}

export function setupUploads(options) {
  hooks = options;
}
