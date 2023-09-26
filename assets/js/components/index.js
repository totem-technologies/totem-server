import { Fragment, h } from "preact"
import Button from "./button"
import Dropdown from "./dropdown"
import register from "./register"

var components = [Button, Dropdown]

export default function () {
  window.h = h
  window.Fragment = Fragment

  components.forEach((c) => {
    register(c, c.tagName, [], { shadow: false })
  })
}
