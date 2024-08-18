import { createSignal } from "solid-js"
import { useTippy } from "solid-tippy"
import { Content } from "tippy.js"
import "tippy.js/dist/tippy.css"
import "tippy.js/themes/light.css"

interface TooltipProps {
  text?: string
  children?: string
  class?: string
}

export function useTotemTip({ content }: { content: Content }) {
  const [anchor, setAnchor] = createSignal<HTMLDivElement>()
  useTippy(anchor, {
    hidden: true,
    props: {
      content: content,
      theme: "light",
    },
  })
  return setAnchor
}

const Tooltip = (props: TooltipProps) => {
  const setAnchor = () => useTotemTip({ content: props.text! })
  return (
    // eslint-disable-next-line solid/no-innerhtml
    <div class={props.class} ref={setAnchor()} innerHTML={props.children} />
  )
}

// export default Avatar
Tooltip.tagName = "t-tooltip"
Tooltip.propsDefault = {
  children: null,
  text: "",
  class: "",
}
export default Tooltip
