import { Fragment, h, render } from "preact"
import { StrictMode, createPortal } from "preact/compat"
import Button from "./button"
import Dropdown from "./dropdown"

var components = {
  Button,
  Dropdown,
}

const InnerHTMLHelper = ({ tagName, html }) =>
  h(tagName, { dangerouslySetInnerHTML: { __html: html } })

function App(props) {
  var d = document.querySelectorAll("[t-component]")
  var c = []
  d.forEach((el) => {
    var name = el.getAttribute("t-component")
    var inner = []
    for (const child of el.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) {
        if (child.textContent.trim() === "") {
          continue
        }
        inner.push(child.textContent)
        continue
      }
      inner.push(child.outerHTML)
    }
    el.innerHTML = ""
    el.hidden = false
    var props = JSON.parse(el.getAttribute("t-props"))
    var comp = components[name]
    if (!comp) {
      console.error(`Component ${name} not found`)
      return
    }
    c.push({ Component: comp, inner, props, el })
  })
  return (
    <StrictMode>
      {c.map((comp) =>
        createPortal(
          <comp.Component {...comp.props}>
            {comp.inner.map((i) => (
              <InnerHTMLHelper tagName="span" html={i} />
            ))}
          </comp.Component>,
          comp.el
        )
      )}
    </StrictMode>
  )
}

export default function () {
  window.h = h
  window.Fragment = Fragment
  render(<App></App>, document.getElementById("app-shell"))
}
