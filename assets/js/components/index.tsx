import { customElement, noShadowDOM } from "solid-element"
import Circles from "./circles"
import PromptSearch from "./promptSearch"
var components = [PromptSearch, Circles]

export default function () {
  components.forEach((c) => {
    customElementWC(c.tagName, c.propsDefault || {}, c)
  })
}

function customElementWC(name: string, propDefaults: any, Component: any) {
  customElement(name, propDefaults, (props: any, { element }) => {
    // Add type annotation for props
    noShadowDOM()
    const slots = element.querySelectorAll("[slot]")
    slots.forEach((slot: any) => {
      // eslint-disable-next-line solid/no-innerhtml
      props[slot.attributes["slot"].value] = <div innerHTML={slot.innerHTML} />
      slot.remove()
    })
    const children = element.innerHTML
    element.innerHTML = ""
    return <Component {...props}>{children}</Component>
  })
}
