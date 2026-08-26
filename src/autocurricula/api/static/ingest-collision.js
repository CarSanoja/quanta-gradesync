const STUDENT_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

const COLLISION_HINT =
  "The file stem is the student id: replace that student's scan, or store this file "
  + "under a different student.";

export function createCollisionGate(dom) {
  let resolveDialog = null;

  function settle(result) {
    if (!resolveDialog) {
      return;
    }
    dom.collisionGate.hidden = true;
    resolveDialog(result);
    resolveDialog = null;
  }

  function confirmRename() {
    if (dom.collisionRenameInput.hidden) {
      dom.collisionRenameInput.hidden = false;
      dom.collisionRenameInput.focus();
      return;
    }
    const name = dom.collisionRenameInput.value.trim();
    if (!STUDENT_ID_RE.test(name)) {
      dom.collisionError.textContent = "Student id: letters, digits, dot, dash or underscore.";
      dom.collisionError.hidden = false;
      return;
    }
    settle({ action: "rename", name });
  }

  dom.collisionCancel.addEventListener("click", () => settle({ action: "cancel" }));
  dom.collisionReplace.addEventListener("click", () => settle({ action: "replace" }));
  dom.collisionRename.addEventListener("click", confirmRename);

  return function askCollision(fileName) {
    dom.collisionMessage.textContent =
      `A scan named ${fileName} already exists in this batch. ${COLLISION_HINT}`;
    dom.collisionRenameInput.hidden = true;
    dom.collisionRenameInput.value = "";
    dom.collisionError.hidden = true;
    dom.collisionGate.hidden = false;
    return new Promise((resolve) => {
      resolveDialog = resolve;
    });
  };
}
