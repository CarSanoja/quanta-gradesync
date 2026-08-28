import { clear, el } from "/console/assets/render.js";

// Each diagram is reached from the screen it explains, not from a gallery.
// The trigger sits beside the section heading, so it lands in the same place
// on every view — which is what makes it safe to hit on camera — while the
// diagram behind it changes with the surface you are looking at.
//
// `context` and `teacher-journey` are deliberately absent: neither describes an
// operator surface. They stay in docs/media for a reader; putting them here to
// round the set up to ten would be the gallery mistake again.
const BY_VIEW = {
  jobs: [
    {
      name: "pipeline",
      label: "Pipeline",
      title: "One job, stage by stage",
      shows: "Inputs, model, cost, checkpoint, and where each stage refuses.",
    },
    {
      name: "resilience",
      label: "Resilience",
      title: "What happens when it breaks",
      shows: "The failure modes that were actually executed, and how each recovers.",
    },
  ],
  review: [
    {
      name: "governance",
      label: "Governance",
      title: "The gates a grade must survive",
      shows: "Every gate before a student record, in the order they apply, with what "
        + "each one stopped.",
    },
  ],
  optimizer: [
    {
      name: "self-improvement",
      label: "Self-improvement",
      title: "How it improves itself",
      shows: "Prompts measured against human ground truth, and the anti-gaming gate "
        + "refusing an unproven change.",
    },
  ],
  fleet: [
    {
      name: "fleet",
      label: "Fleet",
      title: "The twelve components",
      shows: "Model, stage, capability scope and the principal each one acts as.",
    },
  ],
  ingest: [
    {
      name: "exam-lifecycle",
      label: "Lifecycle",
      title: "One exam, end to end",
      shows: "From the front-office scanner to a terminal state, on a real clock, with "
        + "the human entry point marked.",
    },
  ],
  sis: [
    {
      name: "containers",
      label: "Containers",
      title: "Where a grade is written, and by whom",
      shows: "Deployable units, every Firestore collection named, and the identity "
        + "carried on each hop.",
    },
  ],
  trace: [
    {
      name: "architecture",
      label: "Architecture",
      title: "The whole engine",
      shows: "Ingest chain, the seven stages, memory tiers, the harness, and the "
        + "surfaces.",
    },
  ],
};

export function diagramUrl(name) {
  return `/console/diagrams/${name}.svg`;
}

export function diagramsFor(view) {
  return BY_VIEW[view] || [];
}

export function renderTriggers(target, view, onOpen) {
  clear(target);
  diagramsFor(view).forEach((entry) => {
    const trigger = el("button", {
      class: "ghost diagram-trigger",
      type: "button",
      title: `${entry.title} — ${entry.shows}`,
      "aria-label": `Open the diagram: ${entry.title}`,
      text: entry.label,
    });
    // The trigger is handed over explicitly rather than read from
    // document.activeElement: not every browser focuses a button on click, and
    // closing must return the keyboard where it came from.
    trigger.addEventListener("click", () => onOpen(entry, trigger));
    target.append(trigger);
  });
}

export { BY_VIEW };
