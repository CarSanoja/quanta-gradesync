import {
  clear,
  el,
  emptyState,
  formatDateTime,
  formatNumber,
  formatPercent,
  metaRow,
  metric,
  pill,
  table,
} from "./render.js";

export function renderJobsList(target, jobs, activeId, onSelect) {
  clear(target);
  if (!jobs.length) {
    target.append(
      emptyState("No batches yet", "Push a Pub/Sub event or drop a batch into the bucket.")
    );
    return;
  }
  const list = el("div", { class: "list" });
  jobs.forEach((job) => {
    const item = el(
      "button",
      {
        type: "button",
        class: `list-item${job.job_id === activeId ? " is-active" : ""}`,
        onclick: () => onSelect(job.job_id),
      },
      [
        el("span", { class: "list-title" }, [
          el("span", { class: "mono", text: job.job_id }),
          pill(job.stage, job.stage === "completed" ? "succeeded" : job.stage),
        ]),
        metaRow([`${job.subject} · ${job.class_id}`, `updated ${formatDateTime(job.updated_at)}`]),
        el(
          "span",
          { class: "stage-track" },
          job.stages.map((stage) => pill(stage.name, stage.status))
        ),
      ]
    );
    list.append(item);
  });
  target.append(list);
}

function studentRow(student, onOpenReview) {
  const action =
    student.sis_status === "quarantined"
      ? el("button", {
          class: "ghost",
          type: "button",
          text: "Review",
          onclick: () => onOpenReview(student.review_id),
        })
      : el("span", { class: "mono", text: `${student.criteria.length} criteria` });
  return el("tr", {}, [
    el("td", {}, el("span", { class: "mono", text: student.student_id })),
    el("td", { class: "numeric", text: formatPercent(student.percentage) }),
    el("td", {}, pill(student.sis_status, student.sis_status)),
    el("td", {}, action),
  ]);
}

export function renderJobDetail(target, detail, onOpenReview) {
  clear(target);
  if (!detail) {
    target.append(emptyState("Select a batch", "Stage checkpoints appear here."));
    return;
  }
  const job = detail.job;
  target.append(
    el("dl", { class: "metrics" }, [
      metric("Submissions", String(detail.submission_count)),
      metric("Graded", String(detail.graded_count)),
      metric("Synced to SIS", String(detail.synced_count)),
      metric("Quarantined at sync", String(detail.quarantined_count)),
      metric("Failed writes", String(detail.failed_count)),
    ])
  );
  target.append(
    metaRow([
      el("span", { class: "mono", text: `gs://${job.bucket}/${job.exam_batch_prefix}` }),
      `trace ${job.trace_id}`,
      `triggered ${formatDateTime(job.triggered_at)}`,
    ])
  );
  if (job.error) {
    target.append(el("p", { class: "section-title", text: "Failure" }));
    target.append(el("ul", { class: "reasons" }, el("li", { class: "reason", text: job.error })));
  }
  target.append(el("p", { class: "section-title", text: "Pipeline stages" }));
  target.append(
    el(
      "div",
      { class: "stage-track" },
      job.stages.map((stage) => pill(`${stage.name} · ${stage.status}`, stage.status))
    )
  );
  target.append(el("p", { class: "section-title", text: "Students" }));
  if (!detail.students.length) {
    target.append(emptyState("No submissions recorded", "The fetch stage has not completed."));
    return;
  }
  target.append(
    table(
      [
        { label: "Student" },
        { label: "Score", numeric: true },
        { label: "SIS" },
        { label: "" },
      ],
      detail.students.map((student) => studentRow(student, onOpenReview))
    )
  );
}

export function renderReviewList(target, items, activeId, onSelect) {
  clear(target);
  if (!items.length) {
    target.append(emptyState("Queue is clear", "Every graded record cleared the confidence gate."));
    return;
  }
  const list = el("div", { class: "list" });
  items.forEach((item) => {
    list.append(
      el(
        "button",
        {
          type: "button",
          class: `list-item${item.review_id === activeId ? " is-active" : ""}`,
          onclick: () => onSelect(item.review_id),
        },
        [
          el("span", { class: "list-title" }, [
            el("span", { text: item.student_id }),
            pill(`${item.reasons.length} reason${item.reasons.length === 1 ? "" : "s"}`, "quarantined"),
          ]),
          metaRow([item.subject, `queued ${formatDateTime(item.created_at)}`]),
        ]
      )
    );
  });
  target.append(list);
}

function criteriaTable(criteria) {
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
        el("td", {
          class: "numeric",
          text:
            criterion.max_score === null || criterion.max_score === undefined
              ? formatNumber(criterion.score, 1)
              : `${formatNumber(criterion.score, 1)} / ${formatNumber(criterion.max_score, 1)}`,
        }),
        el("td", { class: "numeric", text: formatNumber(criterion.confidence, 3) }),
        el("td", { class: "numeric", text: String(criterion.evidence_count) }),
      ])
    )
  );
}

function evidenceFrame(item, imageUrl) {
  const frame = el("div", { class: "evidence-frame" });
  if (imageUrl) {
    frame.append(el("img", { src: imageUrl, alt: `Scanned page for ${item.student_id}` }));
  } else {
    frame.append(
      emptyState("Scanned page unavailable", "The staged file could not be read in this mode.")
    );
  }
  if (item.evidence.length) {
    frame.append(
      el(
        "div",
        { class: "evidence-overlay" },
        item.evidence.slice(0, 3).map((span) =>
          el("div", { class: "callout" }, [
            el("div", { class: "callout-head" }, [
              el("span", { text: `page ${span.page}` }),
              el("span", { text: "cited evidence" }),
            ]),
            el("div", { class: "callout-quote", text: `“${span.quote}”` }),
            el("div", { class: "callout-why", text: span.rationale }),
          ])
        )
      )
    );
  }
  return frame;
}

export function renderReviewDetail(target, context, handlers) {
  clear(target);
  const item = context.item;
  if (!item) {
    target.append(emptyState("Select a quarantined item", "Reasons, evidence and the scan appear here."));
    return;
  }
  const record = item.proposed_record;
  target.append(
    el("span", { class: "list-title" }, [
      el("span", { text: `${item.student_id} · ${item.subject}` }),
      pill(item.status, item.status),
    ])
  );
  target.append(
    metaRow([
      el("span", { class: "mono", text: item.job_id }),
      `graded ${formatDateTime(record.graded_at)}`,
      record.provenance ? `prompt ${record.provenance.prompt_variant_id}` : "prompt unversioned",
    ])
  );
  target.append(el("p", { class: "section-title", text: "Why it was quarantined" }));
  target.append(
    el(
      "ul",
      { class: "reasons" },
      item.reasons.map((reason) => el("li", { class: "reason", text: reason }))
    )
  );
  target.append(
    el("dl", { class: "metrics" }, [
      metric("Proposed score", formatNumber(record.score, 1)),
      metric("Percentage", formatPercent(record.percentage)),
      metric("Competencies", String(record.competency_codes.length)),
      metric("Evidence spans", String(item.evidence.length)),
    ])
  );
  target.append(el("p", { class: "section-title", text: "Proposed record, criterion by criterion" }));
  target.append(
    context.criteria.length
      ? criteriaTable(context.criteria)
      : emptyState("Criterion detail unavailable", "The job checkpoint no longer holds the grading result.")
  );
  target.append(el("p", { class: "section-title", text: "Teacher feedback" }));
  target.append(el("p", { text: record.feedback }));
  target.append(el("p", { class: "section-title", text: "Scanned page with cited evidence" }));
  target.append(evidenceFrame(item, context.imageUrl));
  if (item.rework_notes.length) {
    target.append(el("p", { class: "section-title", text: "Rework notes" }));
    target.append(
      el(
        "ul",
        { class: "reasons" },
        item.rework_notes.map((note) => el("li", { class: "reason", text: note }))
      )
    );
  }
  target.append(
    el("div", { class: "actions" }, [
      el("button", {
        class: "primary",
        type: "button",
        text: "Approve and write to SIS",
        onclick: () => handlers.onApprove(item.review_id),
      }),
      el("button", {
        class: "ghost",
        type: "button",
        text: "Dismiss",
        onclick: () => handlers.onDismiss(item.review_id),
      }),
    ])
  );
}

function variantCard(variant) {
  const metrics = variant.latest_metrics;
  return el("article", { class: "variant-card" }, [
    el("h4", {}, [
      el("span", { class: "mono", text: variant.variant_id }),
      pill(`v${variant.active_version} · ${variant.source}`, "succeeded"),
    ]),
    el("p", {
      class: "variant-meta",
      text: `${variant.promoted_cycles} promoted cycle(s) · ${variant.few_shot_count} few-shot(s) · provenance ${variant.provenance}`,
    }),
    metrics
      ? el("dl", { class: "metrics" }, [
          metric("MAE", formatNumber(metrics.mae, 3)),
          metric("QWK", formatNumber(metrics.quadratic_weighted_kappa, 3)),
          metric("Bias", formatNumber(metrics.bias, 3)),
        ])
      : el("p", { class: "variant-meta", text: "No promoted calibration metrics yet." }),
    el("pre", { class: "prompt-preview", text: variant.system_instruction }),
  ]);
}

export function renderOptimizer(variantsTarget, cyclesTarget, report) {
  clear(variantsTarget);
  clear(cyclesTarget);
  if (!report.variants.length) {
    variantsTarget.append(emptyState("No prompt variants registered", "Run an optimize stage first."));
  } else {
    variantsTarget.append(
      el("div", { class: "variant-grid" }, report.variants.map(variantCard))
    );
  }
  if (!report.cycles.length) {
    cyclesTarget.append(
      emptyState("No tournament cycles recorded", "Promotions appear once the optimizer accepts a mutation.")
    );
    return;
  }
  cyclesTarget.append(
    table(
      [
        { label: "Variant" },
        { label: "Version", numeric: true },
        { label: "MAE before", numeric: true },
        { label: "MAE after", numeric: true },
        { label: "Δ MAE", numeric: true },
        { label: "QWK after", numeric: true },
        { label: "Outcome" },
      ],
      report.cycles
        .slice()
        .reverse()
        .map((cycle) =>
          el("tr", {}, [
            el("td", {}, el("span", { class: "mono", text: cycle.variant_id })),
            el("td", { class: "numeric", text: String(cycle.version) }),
            el("td", { class: "numeric", text: formatNumber(cycle.previous.mae, 3) }),
            el("td", { class: "numeric", text: formatNumber(cycle.candidate.mae, 3) }),
            el("td", { class: "numeric", text: formatNumber(cycle.delta_mae, 3) }),
            el("td", {
              class: "numeric",
              text: formatNumber(cycle.candidate.quadratic_weighted_kappa, 3),
            }),
            el("td", {}, [
              pill(cycle.accepted ? "promoted" : "rejected", cycle.accepted ? "succeeded" : "failed"),
              cycle.rejected_reasons.length
                ? el("div", { class: "list-sub", text: cycle.rejected_reasons.join("; ") })
                : null,
            ]),
          ])
        )
    )
  );
}
