export default function () {
  const templates = globalThis.document.querySelectorAll(
    "template[shadowrootmode]"
  )
  for (const template of templates) {
    const mode = template.getAttribute("shadowrootmode")
    const shadowRoot = template.parentNode.attachShadow({ mode })
    shadowRoot.appendChild(template.content)
    template.remove()
  }
}
