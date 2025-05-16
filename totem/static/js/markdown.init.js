window.addEventListener("DOMContentLoaded", (event) => {
  const fields = document.querySelectorAll(".markdown-widget")
  for (const field of fields) {
    const height = field.getAttribute("height") || "500px"
    const easyMDE = new window.EasyMDE({
      element: field,
      maxHeight: height,
      minHeight: height,
      spellChecker: false,
      sideBySideFullscreen: false,
    })
  }
});
