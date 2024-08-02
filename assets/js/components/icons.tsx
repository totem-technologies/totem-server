import { AiOutlineClockCircle, AiOutlineDollarCircle } from "solid-icons/ai"
import { FaRegularStar } from "solid-icons/fa"
import { FiRepeat } from "solid-icons/fi"
import { TbArmchair } from "solid-icons/tb"
import { Match, Switch } from "solid-js"

export type IconName = "star" | "dollar" | "recur" | "clock" | "chair"

type IconProps = {
  name: IconName
  size?: number
}

const defaultSize = 20

function Icon(props: IconProps) {
  if (props.size === undefined) {
    props.size = defaultSize
  }
  return (
    <Switch>
      <Match when={props.name === "star"}>
        <FaRegularStar size={props.size} />
      </Match>
      <Match when={props.name === "dollar"}>
        <AiOutlineDollarCircle size={props.size} />
      </Match>
      <Match when={props.name === "recur"}>
        <FiRepeat size={props.size} />
      </Match>
      <Match when={props.name === "clock"}>
        <AiOutlineClockCircle size={props.size} />
      </Match>
      <Match when={props.name === "chair"}>
        <TbArmchair size={props.size} />
      </Match>
    </Switch>
  )
}

Icon.tagName = "t-icon"
Icon.propsDefault = {
  size: defaultSize,
}
export default Icon
