import { useState } from "preact/hooks"

export default function Dropdown(props) {
  var [open, setOpen] = useState(false)
  function toggle() {
    setOpen(!open)
  }
  function close() {
    setTimeout(() => {
      setOpen(false)
    }, 100)
  }
  return (
    <div class="relative">
      <span onClick={toggle} onBlur={close}>
        {props.children[0]}
      </span>
      <div class={`z-10  ${open ? "" : "hidden"}`}>{props.children[1]}</div>
    </div>
  )
}
