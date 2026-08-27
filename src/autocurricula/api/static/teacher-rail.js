import { examCount, plural } from "/teacher/assets/teacher-format.js";

const RAIL_LABELS = {
  home: "Send scans",
  uploading: "Sending",
  grading: "The batch",
  settled: "The batch",
  held: "Needs you",
  review: "One exam",
  grades: "Grades",
};

const dom = {};

export function setupRail(handlers) {
  dom.label = document.getElementById("rail-label");
  dom.bell = document.getElementById("nav-needs");
  dom.mark = document.getElementById("rail-mark");
  dom.resume = document.getElementById("nav-resume");
  dom.mark.addEventListener("click", () => handlers.onHome());
  dom.bell.addEventListener("click", () => handlers.onNeeds());
  dom.resume.addEventListener("click", () => handlers.onResume());
}

export function paintRail(screen, waiting) {
  dom.label.textContent = RAIL_LABELS[screen] || "";
  dom.bell.textContent = String(waiting);
  dom.bell.classList.toggle("is-quiet", waiting < 1);
  dom.bell.setAttribute(
    "aria-label",
    waiting
      ? `${examCount(waiting)} ${plural(waiting, "needs", "need")} you — open them`
      : "Nothing needs you"
  );
  dom.bell.title = waiting ? "These are waiting for you" : "Nothing needs you";
}

export function paintResume(review) {
  if (!review) {
    dom.resume.hidden = true;
    dom.resume.textContent = "";
    return;
  }
  dom.resume.hidden = false;
  dom.resume.textContent = `Back to ${review.student_name}`;
}
