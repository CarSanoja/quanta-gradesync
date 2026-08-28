const SECTIONS = {
  jobs: ["Jobs timeline", "every batch, stage by stage"],
  review: ["Review queue", "what the system refused to decide"],
  optimizer: ["Optimizer", "the system improves itself — here is the record"],
  fleet: ["Fleet", "who each agent is and what it is allowed to touch"],
  ingest: ["Ingest", "the front door"],
  sis: ["SIS ledger", "the grades that actually arrived"],
  trace: ["Mission control", "watch it happen"],
};

const dom = {};

function bind() {
  if (dom.title) {
    return;
  }
  dom.title = document.getElementById("section-title");
  dom.sub = document.getElementById("section-sub");
  dom.reviewBadge = document.getElementById("rail-badge-review");
  dom.liveBadge = document.getElementById("rail-badge-live");
}

export function paintSection(view) {
  bind();
  const [title, sub] = SECTIONS[view] || ["", ""];
  dom.title.textContent = title;
  dom.sub.textContent = sub;
  document.title = title ? `${title} · GradeSync console` : "GradeSync Operations Console";
}

export function paintReviewBadge(count) {
  bind();
  const waiting = Number(count) || 0;
  dom.reviewBadge.textContent = String(waiting);
  dom.reviewBadge.hidden = waiting < 1;
}

export function paintLiveBadge(running) {
  bind();
  dom.liveBadge.hidden = !running;
}
