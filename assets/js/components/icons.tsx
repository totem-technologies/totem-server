import { AiOutlineClockCircle, AiOutlineDollarCircle } from "solid-icons/ai"
import { FaRegularStar } from "solid-icons/fa"
import { FiRepeat } from "solid-icons/fi"
import { TbOutlineChairDirector } from "solid-icons/tb"
import { createMemo, Match, Switch } from "solid-js"

export type IconName = "star" | "dollar" | "recur" | "clock" | "chair"

interface IconProps {
  name: IconName
  size?: number
}

const defaultSize = 20

function Icon(props: IconProps) {
  const size = createMemo(() => props.size ?? defaultSize)

  return (
    <Switch>
      <Match when={props.name === "star"}>
        <FaRegularStar size={size()} />
      </Match>
      <Match when={props.name === "dollar"}>
        <AiOutlineDollarCircle size={size()} />
      </Match>
      <Match when={props.name === "recur"}>
        <FiRepeat size={size()} />
      </Match>
      <Match when={props.name === "clock"}>
        <AiOutlineClockCircle size={size()} />
      </Match>
      <Match when={props.name === "chair"}>
        <TbOutlineChairDirector size={size()} />
      </Match>
    </Switch>
  )
}

Icon.tagName = "t-icon"
Icon.propsDefault = {
  size: defaultSize,
}
export default Icon
