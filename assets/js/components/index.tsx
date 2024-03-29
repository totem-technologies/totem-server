import { customElement, noShadowDOM } from "solid-element"
import DatePickerComponent from "./datePicker"
import PromptSearch from "./promptSearch"
var components = [PromptSearch, DatePickerComponent]

export default function () {
  components.forEach((c) => {
    customElementWC(c.tagName, c.propsDefault || {}, c)
  })
}

function customElementWC(name, propDefaults, Component) {
  customElement(name, propDefaults, (props, { element }) => {
    noShadowDOM()
    const slots = element.querySelectorAll("[slot]")
    slots.forEach((slot) => {
      // eslint-disable-next-line solid/no-innerhtml
      props[slot.attributes["slot"].value] = <div innerHTML={slot.innerHTML} />
      slot.remove()
    })
    const children = element.innerHTML
    element.innerHTML = ""
    console.log("customElementWC", props, element)
    return <Component {...props}>{children}</Component>
  })
}
