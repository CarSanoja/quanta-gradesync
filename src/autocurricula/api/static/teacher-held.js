import { el } from "/console/assets/render.js";
import { examCount, plural } from "/teacher/assets/teacher-format.js";

export const LIST_CAP = 8;
export const FINDER_THRESHOLD = 8;

function finder(ctx, group, count) {
  const input = el("input", {
    type: "search",
    id: `find-${group.key}`,
    placeholder: "Start typing a name",
    autocomplete: "off",
    oninput: (event) => ctx.setQuery(group.key, event.target.value),
  });
  input.value = ctx.queries[group.key] || "";
  return el("label", { class: "finder", for: `find-${group.key}` }, [
    el("span", { text: `Find one of the ${count} by name` }),
    input,
  ]);
}

function matches(items, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) {
    return items;
  }
  return items.filter((item) => item.student_name.toLowerCase().includes(needle)
    || item.student_id.toLowerCase().includes(needle));
}

function judgementSection(ctx, group) {
  const query = ctx.queries[group.key] || "";
  const found = matches(group.items, query);
  const shown = found.slice(0, LIST_CAP);
  const hidden = found.length - shown.length;
  const nodes = [
    el("h2", { text: `${group.count} ${plural(group.count, "needs", "need")} your judgement` }),
    el("p", {
      text: "Something on these pages the system will not decide on its own. You look at them one "
        + "at a time.",
    }),
  ];
  if (group.items.length > FINDER_THRESHOLD) {
    nodes.push(finder(ctx, group, group.count));
  }
  nodes.push(el("ul", { class: "group-list" }, shown.map((item) => el("li", {}, [
    el("button", {
      class: "held-open",
      type: "button",
      onclick: () => ctx.goReview("judgement", item.review_id),
    }, [
      el("span", { class: "group-student", text: item.student_name }),
      el("span", {
        class: "group-reason",
        text: [item.assessment, item.class_id ? `class ${item.class_id}` : "", item.primary_reason]
          .filter(Boolean).join(" · "),
      }),
    ]),
  ]))));
  if (!found.length) {
    nodes.push(el("p", { class: "group-more", text: `No student here matches “${query.trim()}”.` }));
  } else if (hidden > 0) {
    nodes.push(el("p", { class: "group-more", text: `and ${hidden} more` }));
  }
  nodes.push(el("button", {
    class: "primary",
    type: "button",
    text: "Review these one at a time",
    onclick: () => ctx.goReview("judgement"),
  }));
  return el("section", { class: "panel is-flagged", style: "margin-bottom:3.25rem" }, nodes);
}

function precautionSection(ctx, group) {
  const shown = group.items.slice(0, LIST_CAP);
  const hidden = group.items.length - shown.length;
  return el("section", { class: "panel" }, [
    el("h2", { text: `${group.count} ${plural(group.count, "was", "were")} held as a precaution` }),
    el("p", {
      text: "This whole batch was held for a human look as a precaution. Nothing was found wrong "
        + "with these ones — they were held only because they arrived together with the rest.",
    }),
    el("p", { text: "You can send them all to the gradebook in one go." }),
    el("ul", { class: "group-list" }, shown.map((item) => el("li", {}, [
      el("button", {
        class: "held-open",
        type: "button",
        onclick: () => ctx.goReview("batch_hold", item.review_id),
      }, [
        el("span", { class: "group-student", text: item.student_name }),
        el("span", {
          class: "group-reason",
          text: [item.assessment, item.class_id ? `class ${item.class_id}` : ""]
            .filter(Boolean).join(" · "),
        }),
      ]),
    ]))),
    hidden > 0 ? el("p", { class: "group-more", text: `and ${hidden} more` }) : null,
    el("div", { class: "button-row" }, [
      el("button", {
        class: "dark",
        type: "button",
        text: `Put all ${group.count} in the gradebook`,
        onclick: () => ctx.askRelease(),
      }),
      el("button", {
        class: "secondary",
        type: "button",
        text: "Look through them first",
        onclick: () => ctx.goReview("batch_hold"),
      }),
    ]),
  ]);
}

export function renderHeld(host, ctx) {
  const summary = ctx.summary;
  const judged = summary.judgement;
  const held = summary.batch_hold;
  const both = judged.count > 0 && held.count > 0;
  host.className = "screen is-wide";
  host.append(
    el("p", {
      class: "eyebrow",
      text: ctx.batch ? ctx.batch.assessment : "Across your classes",
    }),
    el("h1", {
      class: "display is-small",
      text: `We held ${examCount(summary.waiting_count)} for you.`,
    }),
    el("p", {
      class: "lede",
      text: both
        ? "Almost all of them are fine. They are in two separate groups, and they are settled in "
          + "two different ways."
        : judged.count
          ? "Each of these was held for a reason of its own. You look at them one at a time."
          : "Nothing is wrong with these one by one. The whole batch was held as a precaution, so "
            + "they are all waiting on one decision from you.",
    })
  );
  if (judged.count) {
    host.append(judgementSection(ctx, judged));
  }
  if (held.count) {
    host.append(precautionSection(ctx, held));
  }
}
