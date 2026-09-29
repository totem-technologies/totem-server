(() => {
  const initialize = () => {
    const group = document.getElementById("discussion_prompts-group");
    if (!group) return;

    const tbody = group.querySelector("tbody");
    if (!tbody) return;

    let draggedRow = null;

    const rows = () =>
      Array.from(tbody.querySelectorAll("tr.form-row:not(.empty-form)")).filter((row) =>
        row.querySelector('input[name$="-prompt"]'),
      );

    const activeRows = () =>
      rows().filter((row) => !row.querySelector('input[name$="-DELETE"]:checked'));

    const updatePositions = () => {
      activeRows().forEach((row, index) => {
        const position = row.querySelector('input[name$="-position"]');
        if (position) position.value = index + 1;
      });
    };

    const addDragHandle = (row) => {
      if (row.querySelector(".session-prompt-drag-handle")) return;
      const promptInput = row.querySelector('input[name$="-prompt"]');
      const cell = promptInput?.closest("td");
      if (!cell) return;

      const handle = document.createElement("button");
      handle.type = "button";
      handle.className = "session-prompt-drag-handle";
      handle.textContent = "↕";
      handle.title = "Drag to reorder prompt";
      handle.setAttribute("aria-label", "Drag to reorder prompt");
      handle.draggable = true;
      cell.prepend(handle);
    };

    const initializeRows = () => {
      rows().forEach(addDragHandle);
      updatePositions();
    };

    tbody.addEventListener("dragstart", (event) => {
      if (!event.target.closest(".session-prompt-drag-handle")) return;
      draggedRow = event.target.closest("tr.form-row");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", draggedRow.id);
      draggedRow.classList.add("session-prompt-dragging");
    });

    tbody.addEventListener("dragover", (event) => {
      if (!draggedRow) return;
      const targetRow = event.target.closest("tr.form-row:not(.empty-form)");
      if (!targetRow || targetRow === draggedRow || !rows().includes(targetRow)) return;

      event.preventDefault();
      const insertBefore = event.clientY < targetRow.getBoundingClientRect().top + targetRow.offsetHeight / 2;
      tbody.insertBefore(draggedRow, insertBefore ? targetRow : targetRow.nextElementSibling);
    });

    tbody.addEventListener("dragend", () => {
      if (draggedRow) draggedRow.classList.remove("session-prompt-dragging");
      draggedRow = null;
      updatePositions();
    });

    tbody.addEventListener("change", (event) => {
      if (event.target.matches('input[name$="-DELETE"]')) updatePositions();
    });

    group.closest("form").addEventListener("submit", updatePositions);
    document.addEventListener("formset:added", (event) => {
      if (event.detail.formsetName === "discussion_prompts") initializeRows();
    });

    initializeRows();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
