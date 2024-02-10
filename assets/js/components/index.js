import { Fragment, h } from "preact"
import register from "preact-custom-element"
import NavBar from "./navbar"
import PromptSearch from "./promptSearch"

var components = [PromptSearch, NavBar]

export default function () {
  window.h = h
  window.Fragment = Fragment

  components.forEach((c) => {
    register(c, c.tagName, [], { shadow: false })
  })
}
