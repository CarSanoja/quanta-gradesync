import { el } from "/console/assets/render.js";
import { renderBatch } from "/teacher/assets/teacher-batch.js";
import { gradeRow, openGradeId, openGradeKey } from "/teacher/assets/teacher-grades.js";
import { dropzone, lotFields, setupSummary } from "/teacher/assets/teacher-intake.js";
import { pitchLine, valueBand } from "/teacher/assets/teacher-value.js";
import { examCount, plural, prettyName, whenSent } from "/teacher/assets/teacher-format.js";
import { renderHeld } from "/teacher/assets/teacher-held.js";
import { renderUploading } from "/teacher/assets/teacher-uploading.js";

function batchState(batch) {
  if (!batch.settled) {
    return { text: "still running", tone: "is-waiting-tone" };
  }
  if (batch.waiting_for_you) {
    return { text: "waiting for you", tone: "is-waiting-tone" };
  }
  return { text: "finished", tone: "is-done-tone" };
}

function recentBatches(ctx, title) {
  if (!ctx.summary.batches.length) {
    return null;
  }
  return el("section", { class: "recent-batches", "aria-label": "Recent batches" }, [
    el("h2", { class: "section-title", text: title }),
    el("p", {
      class: "section-note",
      text: "Every batch you have sent stays here. Open one to see it exactly as you left it.",
    }),
    el("ul", { class: "rows" }, ctx.summary.batches.map((batch) => {
      const state = batchState(batch);
      const when = whenSent(batch.started_at);
      return el("li", {}, [
        el("button", {
          class: "row-open",
          type: "button",
          onclick: () => ctx.openBatch(batch.lot_code),
        }, [
          el("span", { class: "row-lead" }, [
            el("span", {}, [
              el("span", { class: "row-name", text: batch.assessment }),
              el("span", {
                class: "row-meta",
                text: `${when ? `${when} · ` : ""}${examCount(batch.received)} · `
                  + `${batch.in_gradebook} in the gradebook`,
              }),
            ]),
          ]),
          el("span", { class: "row-tail" }, [
            el("span", { class: `chip ${state.tone}`, text: state.text }),
            el("span", { class: "row-arrow", "aria-hidden": "true", text: "→" }),
          ]),
        ]),
      ]);
    })),
  ]);
}

export function renderHome(host, ctx) {
  const batch = ctx.batch;
  const complete = batch && batch.settled && batch.in_gradebook >= batch.received;
  const lede = !batch
    ? "Nothing is waiting for your decision. Send the scans of an exam and grading starts on "
      + "its own — when something needs you, it will be waiting here."
    : complete
      ? `All ${examCount(batch.in_gradebook)} from ${batch.assessment} are in the gradebook, and `
        + "your students can see their feedback. When something needs your decision, it will be "
        + "waiting here."
      : `${examCount(batch.received)} from ${batch.assessment} `
        + `${plural(batch.received, "was", "were")} sent. ${examCount(batch.still_grading)} `
        + `${plural(batch.still_grading, "is", "are")} `
        + "still being graded; nothing needs your decision yet.";
  const band = batch ? valueBand(batch) : pitchLine();
  host.className = "screen";
  host.append(
    el("p", { class: "eyebrow", text: batch ? batch.assessment : "Your class" }),
    el("h1", { class: "display", text: "Nothing needs you." }),
    el("p", { class: "lede", text: lede }),
    ...(band ? [band] : []),
    lotFields(ctx),
    dropzone(ctx, "Drop the whole pile here", setupSummary(),
      "Choose files from your computer")
  );
  if (batch) {
    const when = whenSent(batch.started_at);
    host.append(el("div", { class: "last-sent" }, [
      el("span", {
        text: when
          ? `Last sent ${when} — ${examCount(batch.received)}, ${batch.assessment}.`
          : `Most recent batch — ${examCount(batch.received)}, ${batch.assessment}.`,
      }),
      el("button", { class: "linkish", type: "button", text: "Open that batch", onclick: () => ctx.openBatch(batch.lot_code) }),
    ]));
  }
  const recent = recentBatches(ctx, "Batches you have sent");
  if (recent) {
    host.append(recent);
  }
}

export function renderGrades(host, ctx) {
  const query = String(ctx.queries.grades || "").trim().toLowerCase();
  const found = ctx.records.filter((record) =>
    !query || prettyName(record.student_id).toLowerCase().includes(query));
  const input = el("input", {
    type: "search",
    id: "grades-search",
    placeholder: "Ana, Camila, Julián…",
    autocomplete: "off",
    oninput: (event) => ctx.setGradeQuery(event.target.value),
  });
  input.value = ctx.queries.grades || "";
  host.className = "screen is-wide";
  host.append(
    el("p", { class: "eyebrow", text: "Everything graded so far" }),
    el("h1", { class: "display is-small", text: "Recent grades" }),
    el("label", { class: "finder", for: "grades-search" }, [
      el("span", { text: "Search by student name" }),
      input,
    ])
  );
  const recent = recentBatches(ctx, "Recent batches");
  if (recent) {
    host.append(recent);
  }
  if (!ctx.records.length) {
    host.append(el("p", {
      class: "empty-line",
      text: query
        ? `No grade in the full history matches “${ctx.queries.grades.trim()}”.`
        : "No grades are in the gradebook yet. They appear here the moment grading finishes.",
    }));
    return;
  }
  const openId = openGradeId(ctx.queries);
  host.append(el("h2", { class: "section-title", text: "Grade by grade" }));
  host.append(el("ul", { class: "grades" }, found.map((record) =>
    gradeRow(record, openId, (next) => ctx.setQuery(openGradeKey(), next)))));
  host.append(el("p", {
    class: "grades-foot",
    text: query
      ? `${found.length} matching ${plural(found.length, "grade", "grades")} shown from the full history.`
      : `Showing the ${ctx.records.length} most recent. Type a name to find a student.`,
  }));
}

export function screenBuilders() {
  return {
    home: renderHome,
    uploading: renderUploading,
    grading: renderBatch,
    held: renderHeld,
    settled: renderBatch,
    grades: renderGrades,
  };
}
