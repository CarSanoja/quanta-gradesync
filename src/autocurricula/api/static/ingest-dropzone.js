const DRAG_ENTER = ["dragenter", "dragover"];
const DRAG_LEAVE = ["dragleave", "drop"];

function wireDragState(zone, names, dragging) {
  names.forEach((name) =>
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.toggle("is-dragover", dragging);
    })
  );
}

export function wireDropzone(dom, onFiles) {
  dom.dropzone.addEventListener("click", () => dom.fileInput.click());
  dom.dropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      dom.fileInput.click();
    }
  });
  dom.fileInput.addEventListener("change", () => {
    if (dom.fileInput.files.length) {
      onFiles(dom.fileInput.files);
      dom.fileInput.value = "";
    }
  });
  wireDragState(dom.dropzone, DRAG_ENTER, true);
  wireDragState(dom.dropzone, DRAG_LEAVE, false);
  dom.dropzone.addEventListener("drop", (event) => {
    if (event.dataTransfer && event.dataTransfer.files.length) {
      onFiles(event.dataTransfer.files);
    }
  });
}
