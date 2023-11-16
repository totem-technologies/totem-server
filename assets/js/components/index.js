import { Fragment, h } from "preact"
import register from "preact-custom-element"
import Button from "./button"
import Card from "./card"
import Dropdown from "./dropdown"
import NavBar from "./navbar"
import PromptSearch from "./promptSearch"

var components = [Button, Dropdown, PromptSearch, Card, NavBar]

export default function () {
  window.h = h
  window.Fragment = Fragment

  components.forEach((c) => {
    register(c, c.tagName, [], { shadow: false })
  })
}
