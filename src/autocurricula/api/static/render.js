export function el(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attributes).forEach(([key, value]) => {
    if (value === null || value === undefined || value === false) {
      return;
    }
    if (key === "class") {
      node.className = value;
    } else if (key === "text") {
      node.textContent = value;
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      node.setAttribute(key, value === true ? "" : String(value));
    }
  });
  (Array.isArray(children) ? children : [children])
    .filter((child) => child !== null && child !== undefined)
    .forEach((child) => {
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    });
  return node;
}

export function clear(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
  return node;
}

export function pill(label, state) {
  return el("span", { class: "pill", "data-state": state || "pending", text: label });
}

export function metaRow(parts) {
  return el(
    "div",
    { class: "list-sub" },
    parts.filter(Boolean).map((part) => (part instanceof Node ? part : el("span", { text: part })))
  );
}

export function metric(label, value) {
  return el("div", { class: "metric" }, [
    el("dt", { text: label }),
    el("dd", { text: value }),
  ]);
}

export function emptyState(title, hint) {
  return el("div", { class: "empty" }, [el("strong", { text: title }), hint || ""]);
}

export function table(headers, rows) {
  const head = el(
    "thead",
    {},
    el(
      "tr",
      {},
      headers.map((header) =>
        el("th", { class: header.numeric ? "numeric" : null, text: header.label })
      )
    )
  );
  return el("table", {}, [head, el("tbody", {}, rows)]);
}

export function formatDateTime(value) {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(digits);
}

export function formatPercent(value) {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${Number(value).toFixed(1)}%`;
}
