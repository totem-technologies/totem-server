window.addEventListener("DOMContentLoaded", (event) => {
  const fields = document.querySelectorAll(".markdown-widget")
  fields.forEach((field) => {
    const height = field.getAttribute("height") || "500px"
    const easyMDE = new EasyMDE({
      element: field,
      maxHeight: height,
    })
  })
})
