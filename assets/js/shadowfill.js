export default function () {
  globalThis.document
    .querySelectorAll("template[shadowrootmode]")
    .forEach((template) => {
      const mode = template.getAttribute("shadowrootmode")
      const shadowRoot = template.parentNode.attachShadow({ mode })
      shadowRoot.appendChild(template.content)
      template.remove()
    })
}
