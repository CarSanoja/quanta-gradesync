import { getToken, setToken } from "/console/assets/api.js";
import { clear, el } from "/console/assets/render.js";
import { prettyName } from "/teacher/assets/teacher-format.js";

const STUDENT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const TOAST_MS = 4600;

const dom = {};
let toastTimer = null;
let collisionResolver = null;
let confirmAction = null;
let onToken = null;

function bind(ids) {
  ids.forEach((id) => {
    dom[id.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = document.getElementById(id);
  });
}

export function toast(message) {
  dom.toast.textContent = message;
  dom.toast.hidden = false;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { dom.toast.hidden = true; }, TOAST_MS);
}

export function showAlert(message) {
  dom.alertText.textContent = message;
  dom.alert.hidden = !message;
}

export function openGate(message) {
  dom.accessError.textContent = message || "";
  dom.accessError.hidden = !message;
  dom.accessInput.value = getToken();
  dom.accessVeil.hidden = false;
  dom.accessInput.focus();
}

export function closeConfirm() {
  dom.confirmVeil.hidden = true;
  confirmAction = null;
}

export function askConfirm(options) {
  dom.confirmTitle.textContent = options.title;
  dom.confirmBody.textContent = options.body;
  dom.confirmAside.textContent = options.aside || "";
  dom.confirmAside.hidden = !options.aside;
  dom.confirmYes.textContent = options.yes;
  dom.confirmError.hidden = true;
  dom.confirmError.textContent = "";
  confirmAction = options.onYes;
  dom.confirmVeil.hidden = false;
  dom.confirmYes.focus();
}

export function confirmError(message) {
  dom.confirmError.textContent = message;
  dom.confirmError.hidden = false;
}

export function confirmBusy(busy) {
  dom.confirmYes.disabled = busy;
  dom.confirmNo.disabled = busy;
}

export function askCollision(studentId) {
  dom.collisionMessage.textContent =
    `There is already a scan saved for ${prettyName(studentId)} in this assessment. You can `
    + "replace it, or save this one under a different student.";
  dom.collisionNameInput.hidden = true;
  dom.collisionNameInput.value = "";
  dom.collisionError.hidden = true;
  dom.collisionDifferent.textContent = "This is a different student";
  dom.collisionVeil.hidden = false;
  dom.collisionReplace.focus();
  return new Promise((resolve) => { collisionResolver = resolve; });
}

function settleCollision(result) {
  if (collisionResolver) {
    dom.collisionVeil.hidden = true;
    collisionResolver(result);
    collisionResolver = null;
  }
}

export function openZoom(title, source, alt) {
  dom.zoomTitle.textContent = title;
  clear(dom.zoomBody).append(el("img", { src: source, alt }));
  dom.zoomVeil.hidden = false;
  dom.zoomClose.focus();
}

export function activeVeil() {
  return [dom.collisionVeil, dom.zoomVeil, dom.confirmVeil, dom.accessVeil]
    .find((veil) => !veil.hidden) || null;
}

function closeVeil(veil) {
  if (veil === dom.collisionVeil) {
    settleCollision({ action: "cancel" });
  } else if (veil === dom.confirmVeil) {
    closeConfirm();
  } else {
    veil.hidden = true;
  }
}

function trapTab(event, veil) {
  const focusables = [...veil.querySelectorAll("button, input, [href]")]
    .filter((node) => !node.hidden && !node.disabled);
  if (!focusables.length) {
    return;
  }
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  const inside = veil.contains(document.activeElement);
  if (event.shiftKey && (document.activeElement === first || !inside)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !inside)) {
    event.preventDefault();
    first.focus();
  }
}

export function veilKeydown(event) {
  const veil = activeVeil();
  if (!veil) {
    return false;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeVeil(veil);
  } else if (event.key === "Tab") {
    trapTab(event, veil);
  }
  return true;
}

function wireCollision(slugify) {
  dom.collisionCancel.addEventListener("click", () => settleCollision({ action: "cancel" }));
  dom.collisionReplace.addEventListener("click", () => settleCollision({ action: "replace" }));
  dom.collisionDifferent.addEventListener("click", () => {
    if (dom.collisionNameInput.hidden) {
      dom.collisionNameInput.hidden = false;
      dom.collisionDifferent.textContent = "Save under this name";
      dom.collisionNameInput.focus();
      return;
    }
    const name = slugify(dom.collisionNameInput.value);
    if (!STUDENT_ID.test(name)) {
      dom.collisionError.textContent = "Type the student's name, like Ana Torres.";
      dom.collisionError.hidden = false;
      return;
    }
    settleCollision({ action: "rename", name });
  });
}

export function setupDialogs(options) {
  onToken = options.onToken;
  bind([
    "alert", "alert-text", "alert-retry", "toast", "access-veil", "access-form", "access-input",
    "access-error", "access-cancel", "confirm-veil", "confirm-title", "confirm-body",
    "confirm-aside", "confirm-error", "confirm-yes", "confirm-no", "collision-veil",
    "collision-message", "collision-name-input", "collision-error", "collision-cancel",
    "collision-different", "collision-replace", "zoom-veil", "zoom-title", "zoom-body",
    "zoom-close",
  ]);
  dom.confirmNo.addEventListener("click", closeConfirm);
  dom.confirmYes.addEventListener("click", () => { if (confirmAction) { confirmAction(); } });
  dom.zoomClose.addEventListener("click", () => { dom.zoomVeil.hidden = true; });
  dom.alertRetry.addEventListener("click", () => options.onRetry());
  dom.accessCancel.addEventListener("click", () => { dom.accessVeil.hidden = true; });
  dom.accessForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = dom.accessInput.value.trim();
    if (!value) {
      dom.accessError.textContent = "Enter your access code to continue.";
      dom.accessError.hidden = false;
      return;
    }
    setToken(value);
    dom.accessVeil.hidden = true;
    onToken();
  });
  wireCollision(options.slugify);
}
