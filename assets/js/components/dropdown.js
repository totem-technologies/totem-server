import { useRef, useState } from "preact/hooks"
import { Popover } from "react-tiny-popover"

function Dropdown() {
  const wrapperRef = useRef(null)
  var [open, setOpen] = useState(false)
  function toggle() {
    setOpen(!open)
  }
  function close() {
    setOpen(false)
  }

  return (
    <div class="relative" onClick={toggle}>
      <Popover
        isOpen={open}
        positions={["bottom", "left", "right", "top"]}
        content={this.props.menu}
        padding={2}
        onClickOutside={close}
      >
        <span>{this.props.button}</span>
      </Popover>
    </div>
  )
}
Dropdown.tagName = "t-dropdown"

export default Dropdown
