import {
  Placement,
  autoPlacement,
  autoUpdate,
  computePosition,
  shift,
} from "@floating-ui/dom"
import {
  JSXElement,
  createSignal,
  createUniqueId,
  onCleanup,
  onMount,
} from "solid-js"

interface TooltipProps {
  text: string
  children: JSXElement
  class: string
}

const Tooltip = (props: TooltipProps) => {
  let referenceElement: HTMLDivElement
  let floatingElement: HTMLDivElement
  const [placement, setPlacement] = createSignal("top" as Placement)
  const [tipShift, setTipShift] = createSignal({ x: 0, y: 0 } as {
    x: number
    y: number
  })
  const uniqueID = createUniqueId()
  onMount(() => {
    if (!referenceElement || !floatingElement) return
    const cleanup = autoUpdate(referenceElement, floatingElement, update)
    onCleanup(cleanup)
  })

  const update = () => {
    if (!referenceElement || !floatingElement) return

    computePosition(referenceElement, floatingElement, {
      placement: placement(),
      middleware: [
        autoPlacement({ padding: 50, elementContext: "reference" }),
        shift(),
      ],
    }).then((d) => {
      setPlacement(d.placement)
      setTipShift({ x: d.x, y: d.y })
    })
  }

  const tipPlacement = () => {
    switch (placement()) {
      case "top":
        return "tooltip-top"
      case "bottom":
        return "tooltip-bottom"
      case "left":
        return "tooltip-left"
      case "right":
        return "tooltip-right"
    }
  }

  return (
    <div ref={referenceElement!}>
      {/* <style>
        {`
                .${uniqueID}::before {
                    // left: ${tipShift().x}px;
                    // top: ${tipShift().y}px;
                    position: absolute;
                    max-width: 200px;
                }
            `}
      </style> */}
      <div
        innerHTML={props.children as string}
        ref={floatingElement!}
        class={`tooltip ${uniqueID} ${tipPlacement()} ${props.class}`}
        data-tip={props.text}></div>
    </div>
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
