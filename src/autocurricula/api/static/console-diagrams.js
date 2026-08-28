import { clear, el } from "/console/assets/render.js";

// The wording is the catalogue's own, from docs/media/README.md, so the console
// and the repository describe each diagram with the same sentence. The order is
// the argument: the whole engine, then what it refuses, then whether it is real.
const DIAGRAMS = [
  {
    name: "architecture",
    title: "The whole engine",
    level: "overview",
    shows: "Ingest chain, the seven stages, memory tiers, the harness, and the surfaces.",
    who: "Anyone — this is the front door",
  },
  {
    name: "governance",
    title: "The ten gates",
    level: "controls",
    shows: "Every gate a grade must survive before reaching a student record, in the "
      + "order they apply, with what each one stopped.",
    who: "Anyone asking “can I trust this?”",
  },
  {
    name: "containers",
    title: "Deployable units",
    level: "containers",
    shows: "What each unit owns, every Firestore collection named, and the identity "
      + "carried on each hop.",
    who: "An engineer deciding whether this is real",
  },
  {
    name: "fleet",
    title: "The twelve components",
    level: "agents",
    shows: "Model, stage, capability scope and the principal each one acts as.",
    who: "Anyone auditing the agent-fleet claim",
  },
  {
    name: "pipeline",
    title: "One job, stage by stage",
    level: "stages",
    shows: "Inputs, model, cost, checkpoint, and where each stage refuses.",
    who: "Anyone reviewing the engineering",
  },
  {
    name: "self-improvement",
    title: "How it improves itself",
    level: "cold loop",
    shows: "Prompts measured against human ground truth, and the anti-gaming gate "
      + "refusing an unproven change.",
    who: "Anyone assessing the learning claim",
  },
  {
    name: "exam-lifecycle",
    title: "One exam, end to end",
    level: "flow",
    shows: "From the front-office scanner to a terminal state, on a real clock, with "
      + "the human entry point marked.",
    who: "Anyone who wants the story end to end",
  },
  {
    name: "resilience",
    title: "What happens when it breaks",
    level: "flow",
    shows: "The failure modes that were actually executed, and how each recovers.",
    who: "Anyone who has run production systems",
  },
  {
    name: "context",
    title: "The school around it",
    level: "context",
    shows: "Who touches the engine, and what it exchanges with the SIS, the ministry "
      + "standard and Google Cloud.",
    who: "Leadership, a judge, a school",
  },
  {
    name: "teacher-journey",
    title: "What the teacher sees",
    level: "people",
    shows: "Her seven screens — and everything she never sees.",
    who: "Product, design, and school buyers",
  },
];

export function diagramUrl(name) {
  return `/console/diagrams/${name}.svg`;
}

function card(entry, onOpen) {
  return el("button", {
    class: "diagram-card",
    type: "button",
    onclick: () => onOpen(entry),
  }, [
    el("span", { class: "diagram-thumb" }, [
      el("img", { src: diagramUrl(entry.name), alt: "", loading: "lazy" }),
    ]),
    el("span", { class: "diagram-body" }, [
      el("span", { class: "diagram-level", text: entry.level }),
      el("span", { class: "diagram-title", text: entry.title }),
      el("span", { class: "diagram-shows", text: entry.shows }),
      el("span", { class: "diagram-who", text: entry.who }),
    ]),
  ]);
}

export function renderDiagrams(target, onOpen) {
  clear(target);
  target.append(
    el("p", {
      class: "hint diagram-note",
      text: "Hand-authored SVG, every number traceable to a dated report in "
        + "docs/reports. Click one to read it full screen.",
    }),
    el("div", { class: "diagram-grid" }, DIAGRAMS.map((entry) => card(entry, onOpen)))
  );
}

export { DIAGRAMS };
