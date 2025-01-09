export default function () {
  const templates = globalThis.document.querySelectorAll<HTMLTemplateElement>(
    "template[shadowrootmode]"
  )
  for (const template of templates) {
    const mode =
      (template.getAttribute("shadowrootmode") as "open" | "closed" | null) ??
      "open"
    const parent = template.parentNode
    if (parent instanceof HTMLElement) {
      const shadowRoot = parent.attachShadow({ mode })
      shadowRoot.appendChild(template.content)
      template.remove()
    }
  }
}
