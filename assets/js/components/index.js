import { Fragment, h } from "preact"
import register from "./register"

import Button from "./button"
import Card from "./card"
import Dropdown from "./dropdown"
import NavMenu from "./navmenu"
import PromptSearch from "./promptSearch"

var components = [Button, Dropdown, PromptSearch, NavMenu, Card]

export default function () {
  window.h = h
  window.Fragment = Fragment

  components.forEach((c) => {
    register(c, c.tagName, [], { shadow: false })
  })
}
