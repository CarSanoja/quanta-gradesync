import { el } from "/console/assets/render.js";
import { plural } from "/teacher/assets/teacher-format.js";
import { uploads } from "/teacher/assets/teacher-upload.js";

export function pairSection(ctx) {
  const names = uploads.pair.groups.flat();
  const count = names.length;
  return el("section", { class: "panel is-flagged" }, [
    el("h2", { text: names.length === 2 ? "Two files look like one exam" : "Some files look like one exam" }),
    el("p", {
      text: `${names.join(" and ")} look like pages of the same exam. GradeSync grades one file per `
        + `student, so ${count} files become ${count} students in the gradebook.`,
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
        text: `${count} different students`,
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

export function unnamedSection(ctx, waiting) {
  const heading = waiting.length === 1
    ? "1 file still needs a name"
    : `${waiting.length} files still need a name`;
  return el("section", { class: "panel is-flagged" }, [
    el("h2", { text: heading }),
    el("p", {
      text: "These came from a camera, so we cannot tell whose they are. Whatever you type here "
        + "becomes the student's name in the gradebook.",
    }),
    ...waiting.map((row) => namerRow(ctx, row)),
  ]);
}

export function troubleSections(ctx, state) {
  const nodes = [];
  if (state.held.length) {
    nodes.push(el("section", { class: "panel" }, [
      el("h2", { text: `${state.held.length} ${plural(state.held.length, "file is", "files are")} held back` }),
      el("p", { text: "Scan those pages into one PDF, pages in order, then send that single file." }),
      el("ul", { class: "group-list" }, state.held.map((row) =>
        el("li", {}, [el("div", { class: "held-open" }, [
          el("span", { class: "group-student", text: row.label }),
        ])]))),
    ]));
  }
  if (state.failed.length) {
    const retryable = state.failed.some((row) => !row.local);
    nodes.push(el("section", { class: "panel is-broken" }, [
      el("h2", { text: `${state.failed.length} ${plural(state.failed.length, "file did", "files did")} not go through` }),
      el("p", {
        text: "The rest of the batch carried on. You can send these again without picking any "
          + "file a second time.",
      }),
      el("ul", { class: "group-list" }, state.failed.map((row) =>
        el("li", {}, [el("div", { class: "held-open" }, [
          el("span", { class: "group-student", text: row.student || row.name || row.label }),
          el("span", { class: "group-reason", text: row.status }),
        ])]))),
      retryable
        ? el("div", { class: "button-row" }, [
            el("button", {
              class: "dark",
              type: "button",
              text: "Try all of those again",
              onclick: () => ctx.retryFailed(),
            }),
          ])
        : null,
    ]));
  }
  return nodes;
}
