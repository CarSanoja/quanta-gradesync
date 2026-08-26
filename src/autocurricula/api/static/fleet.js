import { clear, el, emptyState, metric, pill, table } from "./render.js";

function shortSha(value) {
  return value ? `${value.slice(0, 12)}…` : "—";
}

function navigate(name, argument) {
  const go = window[name];
  if (typeof go === "function") {
    go(argument);
  }
}

function scopeCell(capabilities) {
  if (!capabilities.length) {
    return el("span", { class: "list-sub", text: "no external capability" });
  }
  return el(
    "span",
    { class: "stage-track" },
    capabilities.map((capability) => pill(capability, "info"))
  );
}

function identityCell(principal) {
  return el("span", {}, [
    el("div", { class: "mono", text: principal.principal_id }),
    el("div", {
      class: "list-sub",
      text: principal.dedicated_service_account
        ? `${principal.service_account} · dedicated${principal.impersonated ? " · impersonated" : ""}`
        : principal.service_account,
    }),
  ]);
}

function agentRow(agent) {
  return el("tr", {}, [
    el("td", { class: "numeric", text: String(agent.fleet_index) }),
    el("td", {}, [
      el("button", {
        class: "ghost agent-link",
        type: "button",
        text: agent.display_name,
        onclick: () => navigate("goToMissionControl", { agentId: agent.agent_id }),
      }),
      el("div", { class: "list-sub", text: agent.role }),
      el("div", { class: "mono list-sub", text: agent.agent_id }),
    ]),
    el("td", {}, [
      el("span", { class: "mono", text: agent.model_id }),
      el("div", { class: "list-sub", text: `${agent.runtime_binding} · ${agent.model_source}` }),
    ]),
    el("td", {}, el("span", { class: "list-sub", text: agent.stages.join(", ") || "—" })),
    el("td", {}, identityCell(agent.principal)),
    el("td", {}, scopeCell(agent.capabilitiesView)),
    el("td", {}, [
      pill(agent.lifecycle, agent.lifecycle === "active" ? "succeeded" : "pending"),
      agent.wired ? null : el("div", { class: "list-sub", text: "not wired in this runtime" }),
      agent.prompt
        ? el("div", {
            class: "list-sub",
            text: `${agent.prompt.variant_id} v${agent.prompt.version} · ${agent.prompt.source}`,
          })
        : null,
      el("div", { class: "mono list-sub", text: shortSha(agent.definition_sha) }),
    ]),
  ]);
}

export function renderFleet(summaryTarget, agentsTarget, report) {
  clear(summaryTarget);
  clear(agentsTarget);
  if (!report.agents.length) {
    agentsTarget.append(
      emptyState("No agents registered", "The registry could not be derived from this runtime.")
    );
    return;
  }
  const models = Object.entries(report.summary.by_model)
    .map(([model, count]) => `${model}×${count}`)
    .join(" · ");
  summaryTarget.append(
    el("dl", { class: "metrics" }, [
      metric("Backend", report.summary.mode),
      metric("Agents", `${report.summary.wired_count}/${report.summary.agent_count} wired`),
      metric("Principals", String(report.summary.principal_count)),
      metric("Dedicated SAs", String(report.summary.dedicated_service_accounts)),
      metric("Models", models || "—"),
      metric("Registry", shortSha(report.summary.registry_sha)),
    ])
  );
  const infrastructure = report.principals.filter(
    (principal) => !principal.principal_id.startsWith("agent://")
  );
  if (infrastructure.length) {
    summaryTarget.append(
      el("p", { class: "section-title", text: "Infrastructure principals" }),
      el(
        "div",
        { class: "list" },
        infrastructure.map((principal) =>
          el("div", { class: "list-item is-static" }, [
            el("span", { class: "list-title" }, [
              el("span", { class: "mono", text: principal.principal_id }),
              pill(
                principal.dedicated_service_account ? "dedicated SA" : "ambient identity",
                principal.dedicated_service_account ? "succeeded" : "pending"
              ),
            ]),
            el("div", { class: "list-sub", text: principal.description }),
            el("div", { class: "list-sub mono", text: principal.service_account }),
            scopeCell(principal.capabilities || []),
          ])
        )
      )
    );
  }
  const byPrincipal = new Map(
    report.principals.map((principal) => [principal.principal_id, principal])
  );
  const rows = report.agents.map((agent) => {
    const principal = byPrincipal.get(agent.principal.principal_id) || agent.principal;
    return agentRow({ ...agent, capabilitiesView: principal.capabilities || [] });
  });
  agentsTarget.append(
    table(
      [
        { label: "#", numeric: true },
        { label: "Agent" },
        { label: "Model" },
        { label: "Stages" },
        { label: "Identity" },
        { label: "Scope" },
        { label: "Status" },
      ],
      rows
    )
  );
}
