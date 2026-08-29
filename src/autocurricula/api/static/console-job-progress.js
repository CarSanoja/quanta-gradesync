// What the live feed knows about each exam that the checkpoint does not yet.
//
// A stage result is persisted when its stage closes, so for the length of the
// grade stage — 568 seconds on the run measured 2026-08-28 — every student row
// reads `pending` even though the model has already answered for most of them.
// The feed carries one span per exam as it finishes, so the truth exists; it
// just lives somewhere else.
//
// These states are deliberately not `synced`. Nothing is committed until the
// stage closes: if the service died mid-stage the work would be redone. The
// row says what is true — answered, not yet written.

export const PROGRESS_SCREENED = "screened";
export const PROGRESS_GRADED = "graded";

const GRADING_PREFIX = "Grading_";
const TRANSCRIPTION_PREFIX = "EvidenceTranscription_";
const ARMOR_NAME = "ArmorScreen";

const LABELS = {
  [PROGRESS_GRADED]: "graded · not written",
  [PROGRESS_SCREENED]: "screened",
};

function entryFor(byExam, key) {
  const current = byExam.get(key);
  if (current) {
    return current;
  }
  const created = { graded: false, screened: false, transcribed: false };
  byExam.set(key, created);
  return created;
}

// Folding rather than rebuilding: every event only ever sets a flag true, so a
// tick can carry the previous map forward and read just the new events. Asking
// for the whole feed each time meant re-reading up to five hundred spans from
// Firestore every two and a half seconds, per open tab.
export function foldEvents(byExam, events) {
  (events || []).forEach((event) => {
    if (event.kind !== "span_end") {
      return;
    }
    const name = event.name || "";
    if (name.startsWith(GRADING_PREFIX)) {
      entryFor(byExam, name.slice(GRADING_PREFIX.length)).graded = true;
      return;
    }
    if (name.startsWith(TRANSCRIPTION_PREFIX)) {
      entryFor(byExam, name.slice(TRANSCRIPTION_PREFIX.length)).transcribed = true;
      return;
    }
    // Armor and the rest are named for the stage, not the exam, so they carry
    // the student on the event instead.
    const student = event.student_id;
    if (student && name === ARMOR_NAME) {
      entryFor(byExam, student).screened = true;
    }
  });
  return byExam;
}

export function progressFromEvents(events) {
  return foldEvents(new Map(), events);
}

// The row keys on submission_id; the feed names some spans by student. Both are
// tried so a batch whose two ids differ still lines up.
export function progressFor(progress, student) {
  if (!(progress instanceof Map)) {
    return null;
  }
  const entry = progress.get(student.submission_id) || progress.get(student.student_id);
  if (!entry) {
    return null;
  }
  if (entry.graded) {
    return PROGRESS_GRADED;
  }
  if (entry.screened || entry.transcribed) {
    return PROGRESS_SCREENED;
  }
  return null;
}

export function progressLabel(state) {
  return LABELS[state] || state;
}

export function countGraded(progress) {
  if (!(progress instanceof Map)) {
    return 0;
  }
  return [...progress.values()].filter((entry) => entry.graded).length;
}
