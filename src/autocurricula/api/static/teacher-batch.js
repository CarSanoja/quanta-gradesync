import { el } from "/console/assets/render.js";
import { examCount, plural, whenSent } from "/teacher/assets/teacher-format.js";
import { BANDS, buildRoster, countBand } from "/teacher/assets/teacher-roster.js";

const BAND_KEY = "band";

function counters(batch, roster) {
  const rows = [
    { n: batch.received, label: "scans arrived", live: false },
    { n: batch.in_gradebook, label: "in the gradebook", live: false },
    { n: batch.waiting_for_you, label: "waiting for you", live: batch.waiting_for_you > 0 },
    batch.settled
      ? { n: batch.could_not_grade, label: "could not be graded", live: false }
      : { n: batch.still_grading, label: "still being graded", live: false },
  ];
  return el("ul", { class: "counters" }, rows.map((row) => el("li", {
    class: `counter${row.live ? " is-live" : ""}`,
  }, [
    el("p", { class: `counter-n${row.live ? " is-waiting-tone" : ""}`, text: String(row.n) }),
    el("p", { class: "counter-label", text: row.label }),
  ])));
}

function attention(ctx, batch) {
  if (!batch.waiting_for_you) {
    return null;
  }
  const held = ctx.summary.batch_hold.count;
  const judged = ctx.summary.judgement.count;
  const parts = [];
  if (judged) {
    parts.push(`${judged} ${plural(judged, "needs", "need")} your judgement`);
  }
  if (held) {
    parts.push(`${held} ${plural(held, "was", "were")} held as a precaution`);
  }
  return el("div", { class: "attention" }, [
    el("p", {
      text: `${examCount(batch.waiting_for_you)} of ${batch.received} are waiting on you`
        + `${parts.length ? `: ${parts.join(", ")}` : ""}.`,
    }),
    el("button", {
      class: "primary",
      type: "button",
      text: "Look at them now",
      onclick: () => ctx.goReview(judged ? "judgement" : "batch_hold"),
    }),
  ]);
}

function filters(ctx, roster, active) {
  const present = BANDS.filter((band) => countBand(roster, band.key) > 0);
  if (present.length < 2) {
    return null;
  }
  const chips = [{ key: "", title: "Everything" }].concat(present).map((band) => el("button", {
    class: `filter${active === band.key ? " is-on" : ""}`,
    type: "button",
    text: band.key ? `${band.title} (${countBand(roster, band.key)})` : `Everything (${roster.length})`,
    onclick: () => ctx.setQuery(BAND_KEY, active === band.key ? "" : band.key),
  }));
  return el("div", { class: "filters" }, chips);
}

function row(entry) {
  const meta = [entry.file, entry.reason].filter(Boolean).join(" · ");
  const inner = [
    el("span", { class: "row-lead" }, [
      el("span", { class: "row-pos", text: entry.position }),
      el("span", {}, [
        el("span", { class: "row-name", text: entry.student }),
        el("span", { class: "row-meta", text: meta }),
      ]),
    ]),
    el("span", { class: "row-tail" }, [
      el("span", { class: `chip ${entry.tone}`, text: entry.chip }),
      el("span", { class: "row-score", text: entry.score }),
      entry.open ? el("span", { class: "row-arrow", "aria-hidden": "true", text: "→" }) : null,
    ]),
  ];
  return el("li", {}, [
    entry.open
      ? el("button", { class: "row-open", type: "button", onclick: entry.open }, inner)
      : el("div", { class: "row-static" }, inner),
  ]);
}

function band(ctx, entry, rows) {
  const nodes = [
    el("div", { class: "group-head" }, [
      el("h2", { class: entry.tone, text: entry.title }),
      el("span", { class: "group-count", text: `${rows.length} of ${ctx.batch.received}` }),
    ]),
    el("p", { class: "section-note", text: entry.note }),
  ];
  if (entry.key === "batch_hold" && rows.length) {
    nodes.push(el("button", {
      class: "dark",
      type: "button",
      style: "margin-bottom:0.875rem",
      text: `Put all ${rows.length} in the gradebook`,
      onclick: () => ctx.askRelease(),
    }));
  }
  nodes.push(el("ul", { class: "rows" }, rows.map(row)));
  return el("section", { class: "group" }, nodes);
}

export function renderBatch(host, ctx) {
  const batch = ctx.batch;
  const roster = buildRoster(ctx);
  const active = String(ctx.queries[BAND_KEY] || "");
  const when = whenSent(batch.started_at);
  const done = batch.settled && batch.in_gradebook >= batch.received;
  host.className = "screen is-wide";
  host.append(
    el("p", {
      class: "eyebrow",
      text: `The batch${when ? ` · sent ${when}` : ""}`,
    }),
    el("h1", {
      class: "display is-small",
      text: done ? `${batch.assessment} is finished.` : batch.assessment,
    }),
    counters(batch, roster)
  );
  const banner = attention(ctx, batch);
  if (banner) {
    host.append(banner);
  } else {
    host.append(el("p", {
      class: "lede",
      text: done
        ? "Every exam is in the gradebook and your students can see their feedback. There is "
          + "nothing left waiting for you."
        : "Nothing needs your decision yet. This page keeps itself up to date — you can close it "
          + "and grading carries on without you.",
    }));
  }
  if (!roster.length) {
    host.append(el("p", {
      class: "empty-line",
      text: "The file list for this batch is not available yet. The counts above are live.",
    }));
    return;
  }
  const chips = filters(ctx, roster, active);
  if (chips) {
    host.append(chips);
  }
  const shown = BANDS.filter((entry) => !active || entry.key === active);
  let painted = 0;
  shown.forEach((entry) => {
    const rows = roster.filter((item) => item.band === entry.key);
    if (!rows.length) {
      return;
    }
    painted += 1;
    host.append(band(ctx, entry, rows));
  });
  if (!painted) {
    host.append(el("div", { class: "group-empty" }, [
      el("p", { text: "Nothing in this batch is in that state any more." }),
      el("button", {
        class: "secondary",
        type: "button",
        text: "Show the whole batch",
        onclick: () => ctx.setQuery(BAND_KEY, ""),
      }),
    ]));
  }
  host.append(el("div", { class: "button-row", style: "margin-top:2.75rem" }, [
    el("button", { class: "secondary", type: "button", text: "See the grades", onclick: () => ctx.goGrades() }),
    el("button", { class: "secondary", type: "button", text: "Send more scans", onclick: () => ctx.goHome() }),
  ]));
}

export { BAND_KEY };
