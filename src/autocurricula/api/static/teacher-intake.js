import { el } from "/console/assets/render.js";
import { uploads } from "/teacher/assets/teacher-upload.js";

const LOT_FIELDS = [
  ["subject", "Subject", "Mathematics"],
  ["classId", "Class", "10A"],
  ["assessment", "Assessment name", "Midterm 1"],
];

export function lotFields(ctx) {
  return el("fieldset", { class: "setup-grid" }, [
    el("legend", { text: "Which assessment is this?" }),
    ...LOT_FIELDS.map(([key, label, placeholder]) => {
      const input = el("input", {
        type: "text",
        id: `lot-${key}`,
        placeholder,
        autocomplete: "off",
        oninput: (event) => ctx.setLot(key, event.target.value),
      });
      input.value = uploads.lot[key];
      return el("label", { class: "field", for: `lot-${key}` }, [el("span", { text: label }), input]);
    }),
  ]);
}

export function setupSummary() {
  const { subject, classId, assessment } = uploads.lot;
  if (!subject || !classId || !assessment) {
    return "Photos or PDFs, in any order and under any file name. Tell us which assessment this "
      + "is, and anything we cannot recognise we ask you about here.";
  }
  return `They go in as ${assessment}, class ${classId}, ${subject.toLowerCase()}. `
    + "You never have to rename a file on your computer.";
}

export function dropzone(ctx, title, hint, label) {
  const zone = el("div", { class: "dropzone" }, [
    el("div", { class: "dropzone-body" }, [
      el("div", { class: "dropzone-words" }, [
        el("p", { class: "dropzone-title", text: title }),
        el("p", { class: "dropzone-hint", text: hint }),
      ]),
      el("button", { class: "primary", type: "button", text: label, onclick: () => ctx.pickFiles() }),
    ]),
  ]);
  zone.addEventListener("click", (event) => {
    if (event.target.tagName !== "BUTTON") {
      ctx.pickFiles();
    }
  });
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.add("is-dragover");
  }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragover");
  }));
  zone.addEventListener("drop", (event) => {
    if (event.dataTransfer && event.dataTransfer.files.length) {
      ctx.stageFiles(event.dataTransfer.files);
    }
  });
  return zone;
}
