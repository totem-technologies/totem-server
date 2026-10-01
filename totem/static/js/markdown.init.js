function initMarkdownFields(root) {
  const fields = root.querySelectorAll(".markdown-widget")
  for (const field of fields) {
    // Skip the admin inline "empty-form" template. Django clones it when adding
    // a new inline row, and an editor built on it would be cloned as dead DOM.
    // New rows are initialized via the formset:added event below.
    if (field.name.includes("__prefix__")) continue
    const height = field.getAttribute("height") || "500px"
    field.easyMDE = new window.EasyMDE({
      element: field,
      maxHeight: height,
      minHeight: height,
      spellChecker: false,
      sideBySideFullscreen: false,
      autoDownloadFontAwesome: false,
    })
  }
}

window.addEventListener("DOMContentLoaded", (_) => {
  initMarkdownFields(document)
})

document.addEventListener("formset:added", (event) => {
  initMarkdownFields(event.target)
})

// Editors inside collapsed admin fieldsets are created while hidden, so
// CodeMirror needs a refresh once the section is opened to lay itself out.
document.addEventListener(
  "toggle",
  (event) => {
    if (!event.target.open) return
    for (const field of event.target.querySelectorAll(".markdown-widget")) {
      field.easyMDE?.codemirror.refresh()
    }
  },
  true,
)
