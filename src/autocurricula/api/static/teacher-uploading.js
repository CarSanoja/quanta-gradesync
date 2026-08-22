import { el } from "/console/assets/render.js";
import { plural } from "/teacher/assets/teacher-format.js";
import { uploads, uploadState } from "/teacher/assets/teacher-upload.js";

function lotFields(ctx) {
  const fields = [
    ["subject", "Subject", "Mathematics"],
    ["classId", "Class", "10A"],
    ["assessment", "Assessment name", "Midterm 1"],
  ];
  return el("fieldset", { class: "lot-fields" }, [
    el("legend", { text: "Which assessment is this?" }),
    ...fields.map(([key, label, placeholder]) => {
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

function pairSection(ctx) {
  const names = uploads.pair.groups.flat();
  return el("section", { class: "panel is-flagged" }, [
    el("h2", { text: names.length === 2 ? "Two files look like one exam" : "Some files look like one exam" }),
    el("p", {
      text: `${names.join(" and ")} look like pages of the same exam. GradeSync grades one file per `
        + "student, so two files become two students in the gradebook.",
    }),
    el("div", { class: "pair-thumbs" }, names.map((name) =>
      el("div", { class: "thumb" }, [el("span", { text: name })]))),
    el("div", { class: "button-row" }, [
      el("button", {
        class: "primary",
        type: "button",
        text: "One exam — I'll send them as one PDF",
        onclick: () => ctx.answerPair("combine"),
      }),
      el("button", {
        class: "secondary",
        type: "button",
        text: "Two different students",
        onclick: () => ctx.answerPair("separate"),
      }),
    ]),
  ]);
}

function namerRow(ctx, row) {
  const input = el("input", {
    type: "text",
    id: `namer-${row.id}`,
    placeholder: "Type the student's name",
    autocomplete: "off",
    spellcheck: "false",
    oninput: (event) => ctx.renameRow(row.id, event.target.value),
  });
  input.value = row.name;
  const named = Boolean(row.studentId);
  return el("div", { class: "namer" }, [
    el("div", { class: "namer-thumb" }, row.thumbUrl
      ? [el("img", { src: row.thumbUrl, alt: `Photo ${row.label}` })]
      : []),
    el("div", { class: "namer-body" }, [
      el("p", { class: "namer-file", text: row.label }),
      el("label", { for: `namer-${row.id}`, text: "Whose exam is this?" }),
      input,
      row.note ? el("p", { class: "mark-note", text: row.note }) : null,
    ]),
    named
      ? el("span", { class: "namer-state is-done" }, [
          el("span", { class: "glyph", "aria-hidden": "true", text: "✓" }),
          el("span", { text: "Named" }),
        ])
      : el("span", { class: "namer-state", text: "Waiting for a name" }),
  ]);
}

function unnamedSection(ctx, waiting) {
  const heading = waiting.length === 1
    ? "1 file still needs a name"
    : `${waiting.length} files still need a name`;
  return el("section", { class: "panel" }, [
    el("h2", { text: heading }),
    el("p", {
      text: "These came from a camera, so we cannot tell whose they are. Whatever you type here "
        + "becomes the student's name in the gradebook.",
    }),
    ...waiting.map((row) => namerRow(ctx, row)),
  ]);
}

function troubleSection(ctx, state) {
  const nodes = [];
  if (state.held.length) {
    nodes.push(el("section", { class: "panel" }, [
      el("h2", { text: `${state.held.length} ${plural(state.held.length, "file is", "files are")} held back` }),
      el("p", { text: "Scan those pages into one PDF, pages in order, then send that single file." }),
      el("ul", { class: "group-list" }, state.held.map((row) =>
        el("li", {}, [el("span", { class: "group-student", text: row.label })]))),
    ]));
  }
  if (state.failed.length) {
    nodes.push(el("section", { class: "panel" }, [
      el("h2", { text: `${state.failed.length} ${plural(state.failed.length, "file did", "files did")} not go through` }),
      el("ul", { class: "group-list" }, state.failed.map((row) =>
        el("li", {}, [
          el("span", { class: "group-student", text: row.label }),
          el("span", { class: "group-reason", text: row.status }),
        ]))),
      el("div", { class: "button-row" }, [
        el("button", { class: "secondary", type: "button", text: "Try those again", onclick: () => ctx.retryFailed() }),
      ]),
    ]));
  }
  return nodes;
}

export function renderUploading(host, ctx) {
  const state = uploadState();
  const arrived = state.sent >= state.total && state.total > 0
    ? `All ${state.total} ${plural(state.total, "file", "files")} arrived.`
    : `${state.sent} of ${state.total} ${plural(state.total, "file has", "files have")} arrived.`;
  host.className = "screen";
  host.append(
    el("h1", { class: "display is-small", text: "Your scans are arriving" }),
    lotFields(ctx),
    el("p", { class: "lede", style: "margin-bottom:1.25rem", text: arrived }),
    el("div", { class: "progress-track" }, [
      el("span", {
        class: "progress-fill",
        style: `width:${state.total ? Math.round((state.sent / state.total) * 100) : 0}%`,
      }),
    ]),
    el("p", {
      class: "note",
      style: "margin-bottom:3rem",
      text: state.awaitingLot
        ? "Fill in the three boxes above and sending starts on its own."
        : "You can leave this page — sending continues on its own.",
    })
  );
  if (uploads.pair) {
    host.append(pairSection(ctx));
  }
  const waiting = state.needsName;
  if (waiting.length) {
    host.append(unnamedSection(ctx, waiting));
  }
  troubleSection(ctx, state).forEach((node) => host.append(node));
  host.append(el("div", { class: "button-row", style: "margin-top:2.25rem" }, [
    el("button", { class: "primary", type: "button", text: "Done — start grading", onclick: () => ctx.goGrading() }),
  ]));
}
