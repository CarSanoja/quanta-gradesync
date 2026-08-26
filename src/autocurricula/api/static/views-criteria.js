import { el, formatNumber, table } from "./render.js";

function scoreText(criterion) {
  if (criterion.max_score === null || criterion.max_score === undefined) {
    return formatNumber(criterion.score, 1);
  }
  return `${formatNumber(criterion.score, 1)} / ${formatNumber(criterion.max_score, 1)}`;
}

export function criteriaTable(criteria) {
  return table(
    [
      { label: "Criterion" },
      { label: "Score", numeric: true },
      { label: "Confidence", numeric: true },
      { label: "Evidence", numeric: true },
    ],
    criteria.map((criterion) =>
      el("tr", {}, [
        el("td", {}, [
          el("span", { class: "mono", text: criterion.criterion_id }),
          el("div", { class: "list-sub", text: criterion.comment }),
        ]),
        el("td", { class: "numeric", text: scoreText(criterion) }),
        el("td", { class: "numeric", text: formatNumber(criterion.confidence, 3) }),
        el("td", { class: "numeric", text: String(criterion.evidence_count) }),
      ])
    )
  );
}

export function scoreCeiling(criteria) {
  if (!criteria.length) {
    return null;
  }
  let total = 0;
  for (const criterion of criteria) {
    if (typeof criterion.max_score !== "number") {
      return null;
    }
    total += criterion.max_score;
  }
  return total;
}
