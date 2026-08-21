import { clear, el } from "/console/assets/render.js";

const EM_DASH = "—";

export function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) return EM_DASH;
  if (minutes <= 0) return "done";
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

export function heroNote(summary) {
  const total = summary.waiting_count;
  if (!total) return "";
  const judged = summary.judgement.count;
  const held = summary.batch_hold.count;
  if (judged && held) {
    const one = judged === 1 ? "needs" : "need";
    const rest = held === 1 ? "is" : "are";
    return `${total} exams are on hold. ${judged} ${one} your judgement one by one; the other `
      + `${held} ${rest} held only by the batch rule and go out together.`;
  }
  if (judged) {
    return judged === 1
      ? "One exam needs your judgement before its grade goes out."
      : `${judged} exams need your judgement before their grades go out.`;
  }
  return held === 1
    ? "One exam is held only by the batch rule — nothing is wrong with it."
    : `${held} exams are held only by the batch rule — nothing is wrong with them.`;
}

export function renderCounts(nodes, summary, syncedCount) {
  if (!summary) {
    nodes.strip.hidden = true;
    return;
  }
  const batch = summary.batch;
  nodes.waiting.textContent = String(summary.waiting_count);
  nodes.synced.textContent = String(batch ? batch.in_gradebook : syncedCount);
  nodes.grading.textContent = batch ? String(batch.still_grading) : EM_DASH;
  nodes.time.textContent = batch ? formatMinutes(batch.minutes_left) : EM_DASH;
  nodes.strip.hidden = false;
}

export function idleCopy(summary) {
  const judged = summary.judgement.count;
  const held = summary.batch_hold.count;
  if (judged) {
    return {
      line: judged === 1
        ? "One exam is waiting for your judgement."
        : `${judged} exams are waiting for your judgement.`,
      hint: "Pick a name on the left to open it — the page, the quoted line and the proposed "
        + "grade land here, side by side. Or press “Review one at a time” and we walk you "
        + "through them.",
    };
  }
  if (held) {
    return {
      line: held === 1
        ? "One exam is held only by the batch rule."
        : `${held} exams are held only by the batch rule.`,
      hint: "Nothing is wrong with them one by one. Open any name on the left to read it, or "
        + "release the whole group in a single decision.",
    };
  }
  return { line: "", hint: "" };
}

function briefColumn(group) {
  return el("div", { class: "brief-column", "data-group": group.key }, [
    el("h3", { text: group.title }),
    el("ul", { class: "brief-reasons" }, group.reasons.map((reason) =>
      el("li", {}, [
        el("span", { class: "brief-tally", text: String(reason.count) }),
        el("span", { class: "brief-label", text: reason.label }),
      ])
    )),
  ]);
}

export function renderIdle(nodes, summary, visible) {
  nodes.panel.hidden = !visible;
  if (!visible || !summary) {
    return;
  }
  const copy = idleCopy(summary);
  nodes.line.textContent = copy.line;
  nodes.hint.textContent = copy.hint;
  clear(nodes.brief);
  [summary.judgement, summary.batch_hold]
    .filter((group) => group.count && group.reasons.length)
    .forEach((group) => nodes.brief.append(briefColumn(group)));
}
