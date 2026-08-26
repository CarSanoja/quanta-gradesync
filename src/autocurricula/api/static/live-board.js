import { clear, el, emptyState, pill } from "./render.js";

const IDLE = { calls: 0, tokens: 0, errors: 0, lastSeq: 0, active: false, done: false };
const ACTIVE_WINDOW_MS = 5000;

function statusPill(entry) {
  if (entry.active) {
    return pill("working", "running");
  }
  if (entry.errors) {
    return pill(`${entry.errors} error${entry.errors === 1 ? "" : "s"}`, "failed");
  }
  if (entry.done) {
    return pill("done", "succeeded");
  }
  return pill("idle", "pending");
}

function stageChips(stages) {
  if (!stages || !stages.length) {
    return el("div", { class: "agent-meta", text: "no stage binding" });
  }
  return el("div", { class: "stage-track" }, stages.map((stage) => pill(stage, "pending")));
}

function principalOf(agent) {
  const principal = agent.principal || {};
  return principal.principal_id || "ambient identity";
}

function cardClass(entry) {
  const classes = ["agent-card"];
  if (entry.active) {
    classes.push("is-active");
  }
  if (entry.errors) {
    classes.push("is-error");
  }
  if (entry.done && !entry.active) {
    classes.push("is-done");
  }
  return classes.join(" ");
}

function agentCard(agent, entry) {
  return el("div", { class: cardClass(entry) }, [
    el("div", { class: "agent-name" }, [
      el("span", { text: agent.display_name || agent.agent_id }),
      statusPill(entry),
    ]),
    el("div", { class: "agent-meta" }, [
      el("span", { class: "mono", text: agent.model_id || "deterministic" }),
      agent.lifecycle && agent.lifecycle !== "active"
        ? el("span", { text: agent.lifecycle })
        : null,
    ]),
    el("div", { class: "agent-meta" }, el("span", { class: "mono", text: principalOf(agent) })),
    stageChips(agent.stages),
    el("div", { class: "agent-meta" }, [
      el("span", { text: `${entry.calls} call${entry.calls === 1 ? "" : "s"}` }),
      el("span", { text: `${entry.tokens.toLocaleString()} tok` }),
    ]),
  ]);
}

export function boardActivity(events, settled, newest) {
  const activity = new Map();
  events.forEach((event) => {
    if (!event.agent_id) {
      return;
    }
    const entry = activity.get(event.agent_id) || { ...IDLE, lastAt: 0 };
    if (event.kind === "llm_call") {
      entry.calls += 1;
      entry.tokens += (event.llm && Number(event.llm.total_tokens)) || 0;
    }
    if (event.status === "error") {
      entry.errors += 1;
    }
    entry.lastSeq = Math.max(entry.lastSeq, event.seq || 0);
    const at = Date.parse(event.recorded_at);
    if (event.kind !== "span_end" && !Number.isNaN(at)) {
      entry.lastAt = Math.max(entry.lastAt, at);
    }
    activity.set(event.agent_id, entry);
  });
  activity.forEach((entry) => {
    entry.active = !settled && newest - entry.lastAt <= ACTIVE_WINDOW_MS;
    entry.done = settled && entry.lastSeq > 0;
  });
  return activity;
}

function agentsFromEvents(events) {
  const agents = new Map();
  events.forEach((event) => {
    if (!event.agent_id) {
      return;
    }
    const agent = agents.get(event.agent_id) || {
      agent_id: event.agent_id,
      display_name: event.agent_id,
      model_id: "",
      stages: [],
      principal: { principal_id: event.principal || "" },
    };
    if (event.llm && event.llm.model) {
      agent.model_id = event.llm.model;
    }
    if (event.stage && !agent.stages.includes(event.stage)) {
      agent.stages.push(event.stage);
    }
    agents.set(event.agent_id, agent);
  });
  return [...agents.values()];
}

export function boardAgents(fleet, events) {
  return fleet && fleet.length ? fleet : agentsFromEvents(events);
}

export function renderBoard(target, fleetAgents, activity) {
  clear(target);
  const agents = Array.isArray(fleetAgents) ? fleetAgents : [];
  if (!agents.length) {
    target.append(
      emptyState(
        "No fleet agents yet",
        "The board fills in as the registry loads or the first agent reports."
      )
    );
    return;
  }
  const entries = activity instanceof Map ? activity : new Map();
  target.append(
    el(
      "div",
      { class: "agent-grid" },
      agents.map((agent) => agentCard(agent, { ...IDLE, ...(entries.get(agent.agent_id) || {}) }))
    )
  );
}
