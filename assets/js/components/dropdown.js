import { useEffect, useRef, useState } from "preact/hooks"

function useOutsideAlerter(ref, cb) {
  useEffect(() => {
    /**
     * Alert if clicked on outside of element
     */
    function handleClickOutside(event) {
      if (ref.current && !ref.current.contains(event.target)) {
        cb()
      }
    }
    // Bind the event listener
    document.addEventListener("mousedown", handleClickOutside)
    return () => {
      // Unbind the event listener on clean up
      document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [ref])
}

function Dropdown() {
  const wrapperRef = useRef(null)
  var [open, setOpen] = useState(false)
  function toggle() {
    setOpen(!open)
  }
  function close() {
    setOpen(false)
  }
  useOutsideAlerter(wrapperRef, close)

  return (
    <div
      class="relative"
      onBlur={close}
      onFocus={() => {
        setOpen(true)
      }}
      onClick={toggle}
    >
      <span ref={wrapperRef}>{this.props.button}</span>
      <div hidden={!open} class={`absolute right-0 z-10`}>
        {this.props.menu}
      </div>
    </div>
  )
}
Dropdown.tagName = "t-dropdown"

export default Dropdown
