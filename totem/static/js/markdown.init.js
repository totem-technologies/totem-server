window.addEventListener("DOMContentLoaded", (_) => {
  const fields = document.querySelectorAll(".markdown-widget")
  for (const field of fields) {
    const height = field.getAttribute("height") || "500px"
    const _easyMDE = new window.EasyMDE({
      element: field,
      maxHeight: height,
      minHeight: height,
      spellChecker: false,
      sideBySideFullscreen: false,
      autoDownloadFontAwesome: false,
    })
  }
})
