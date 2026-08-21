import { clear, el } from "/console/assets/render.js";
import { prettySubject, timeAgo } from "/teacher/assets/teacher-detail.js";

export const FINDER_THRESHOLD = 8;
export const LIST_CAP = 8;
export const MAX_SHEETS = 14;

function sheetCount(count) {
  return Math.max(0, Math.min(count, MAX_SHEETS));
}

export function renderStack(host, count) {
  clear(host);
  if (!count) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  const sheets = sheetCount(count);
  const leaves = el("span", { class: "stack-leaves" });
  for (let index = 0; index < sheets; index += 1) {
    leaves.append(el("span", {
      class: "sheet-leaf",
      style: `--leaf:${index}; --leaves:${sheets}; --step:${sheets > 6 ? 2.2 : 5}px`,
    }));
  }
  host.append(leaves, el("span", { class: "stack-count" }, [
    el("strong", { text: String(count) }),
    el("span", { text: count === 1 ? "exam" : "exams" }),
  ]));
}

export function renderReasons(host, reasons) {
  clear(host);
  host.hidden = !reasons.length;
  reasons.forEach((reason) => {
    host.append(el("li", { class: "reason-count", "data-key": reason.key }, [
      el("span", { class: "reason-tally", text: String(reason.count) }),
      el("span", { class: "reason-label", text: reason.label }),
    ]));
  });
}

function queueRow(item, handlers, withReason) {
  const open = handlers.isOpen(item.review_id);
  return el("li", {}, [
    el("button", {
      type: "button",
      class: `queue-row${open ? " is-open" : ""}`,
      "aria-expanded": open ? "true" : "false",
      onclick: () => handlers.onOpen(item.review_id),
    }, [
      el("span", { class: "queue-student", text: item.student_name }),
      el("span", {
        class: "queue-when",
        text: `${prettySubject(item.subject)} · ${timeAgo(item.waiting_since)}`,
      }),
      withReason ? el("span", { class: "queue-reason", text: item.primary_reason }) : null,
    ]),
  ]);
}

export function filterItems(items, query) {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return items;
  }
  return items.filter((item) => item.student_name.toLowerCase().includes(needle)
    || item.student_id.toLowerCase().includes(needle));
}

export function renderQueue(nodes, items, query, handlers, withReason) {
  const matches = filterItems(items, query);
  const shown = matches.slice(0, LIST_CAP);
  clear(nodes.list);
  shown.forEach((item) => nodes.list.append(queueRow(item, handlers, withReason)));
  nodes.list.hidden = !shown.length;
  const hidden = matches.length - shown.length;
  nodes.more.hidden = hidden <= 0;
  nodes.more.textContent = hidden > 0 ? `and ${hidden} more` : "";
  nodes.finder.hidden = items.length <= FINDER_THRESHOLD;
  if (!matches.length && items.length) {
    nodes.list.hidden = true;
    nodes.more.hidden = false;
    nodes.more.textContent = `No student here matches “${query.trim()}”.`;
  }
}

function countText(count) {
  return count === 1 ? "1 exam" : `${count} exams`;
}

export function renderGroup(nodes, group, query, handlers) {
  const empty = group.count === 0;
  nodes.count.textContent = empty ? "" : countText(group.count);
  nodes.count.hidden = empty;
  nodes.note.textContent = empty ? "" : group.note;
  nodes.note.hidden = empty;
  nodes.empty.textContent = group.empty_note;
  nodes.empty.hidden = !empty;
  nodes.action.hidden = empty;
  nodes.hint.hidden = empty;
  nodes.card.classList.toggle("is-empty", empty);
  renderStack(nodes.stack, group.count);
  renderReasons(nodes.reasons, empty ? [] : group.reasons);
  if (empty) {
    clear(nodes.list);
    nodes.list.hidden = true;
    nodes.more.hidden = true;
    nodes.finder.hidden = true;
    return;
  }
  renderQueue(nodes, group.items, query, handlers, group.reasons.length > 1);
}

export function releaseLabel(count) {
  return count === 1 ? "Release the 1 exam" : `Release all ${count}`;
}

export function releaseMessage(count) {
  return count === 1
    ? "This grade goes straight into the gradebook, exactly as proposed."
    : `All ${count} grades go straight into the gradebook, exactly as proposed.`;
}
