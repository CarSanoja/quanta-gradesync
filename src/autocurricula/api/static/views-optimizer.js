import { clear, el, emptyState, formatNumber, metric, pill, table } from "./render.js";

const LEGEND =
  "MAE = mean absolute score error in rubric points (lower is better) · " +
  "QWK = agreement with the teacher key, 0-1 (higher is better) · " +
  "a variant is promoted only when Δ MAE is negative.";

const CYCLES_EMPTY_HINT =
  "A mutation is promoted only when MAE improves and QWK and bias do not regress. " +
  "Nothing has cleared that bar yet.";

function pairedCell(before, after) {
  return el("td", {
    class: "numeric",
    text: `${formatNumber(before, 3)} → ${formatNumber(after, 3)}`,
  });
}

function deltaCell(value) {
  const sign = value > 0 ? "+" : "";
  return el("td", { class: "numeric", text: `${sign}${formatNumber(value, 3)}` });
}

function variantCard(variant) {
  const metrics = variant.latest_metrics;
  const preview = el("pre", {
    class: "prompt-preview",
    text: variant.system_instruction,
    hidden: true,
  });
  const toggle = el("button", {
    class: "ghost",
    type: "button",
    text: "Show system instruction",
    onclick: () => {
      preview.hidden = !preview.hidden;
      toggle.textContent = preview.hidden ? "Show system instruction" : "Hide system instruction";
    },
  });
  return el("article", { class: "variant-card" }, [
    el("h4", {}, [
      el("span", { class: "mono", text: variant.variant_id }),
      pill(`v${variant.active_version} · ${variant.source}`, "succeeded"),
    ]),
    el("p", {
      class: "variant-meta",
      text:
        `${variant.promoted_cycles} promoted cycle(s) · ${variant.few_shot_count} few-shot(s) · ` +
        `provenance ${variant.provenance}`,
    }),
    metrics
      ? el("dl", { class: "metrics" }, [
          metric("MAE", formatNumber(metrics.mae, 3)),
          metric("QWK", formatNumber(metrics.quadratic_weighted_kappa, 3)),
          metric("Bias", formatNumber(metrics.bias, 3)),
        ])
      : el("p", { class: "variant-meta", text: "No promoted calibration metrics yet." }),
    el("div", { class: "variant-actions" }, toggle),
    preview,
  ]);
}

function cycleRow(cycle) {
  return el("tr", {}, [
    el("td", {}, el("span", { class: "mono", text: cycle.variant_id })),
    el("td", { class: "numeric", text: String(cycle.version) }),
    pairedCell(cycle.previous.mae, cycle.candidate.mae),
    deltaCell(cycle.delta_mae),
    pairedCell(
      cycle.previous.quadratic_weighted_kappa,
      cycle.candidate.quadratic_weighted_kappa
    ),
    deltaCell(
      cycle.candidate.quadratic_weighted_kappa - cycle.previous.quadratic_weighted_kappa
    ),
    pairedCell(cycle.previous.bias, cycle.candidate.bias),
    deltaCell(cycle.candidate.bias - cycle.previous.bias),
    el("td", {}, [
      pill(cycle.accepted ? "promoted" : "rejected", cycle.accepted ? "succeeded" : "failed"),
      cycle.rejected_reasons.length
        ? el("div", { class: "list-sub", text: cycle.rejected_reasons.join("; ") })
        : null,
    ]),
  ]);
}

function cyclesTable(cycles) {
  return table(
    [
      { label: "Variant" },
      { label: "Version", numeric: true },
      { label: "MAE before → after", numeric: true },
      { label: "Δ MAE", numeric: true },
      { label: "QWK before → after", numeric: true },
      { label: "Δ QWK", numeric: true },
      { label: "Bias before → after", numeric: true },
      { label: "Δ bias", numeric: true },
      { label: "Outcome" },
    ],
    cycles.slice().reverse().map(cycleRow)
  );
}

export function renderOptimizer(variantsTarget, cyclesTarget, report) {
  clear(variantsTarget);
  clear(cyclesTarget);
  if (!report.variants.length) {
    variantsTarget.append(
      emptyState("No prompt variants registered", "Run an optimize stage first.")
    );
  } else {
    variantsTarget.append(el("div", { class: "variant-grid" }, report.variants.map(variantCard)));
  }
  cyclesTarget.append(el("p", { class: "hint", text: LEGEND }));
  cyclesTarget.append(
    report.cycles.length
      ? cyclesTable(report.cycles)
      : emptyState("No tournament cycles recorded", CYCLES_EMPTY_HINT)
  );
}
