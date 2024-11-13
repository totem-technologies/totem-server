import _Avatar from "@totem.org/solid-boring-avatars"
import { type JSXElement, Show } from "solid-js"
import { useTotemTip } from "./tooltip"

import type { ProfileAvatarTypeEnum } from "../client"
function Avatar(props: {
  size?: number
  name?: string
  seed?: string
  tooltip?: boolean
  url?: string
  type?: ProfileAvatarTypeEnum
  children?: JSXElement
}) {
  const setAnchor = () => {
    if (props.tooltip) {
      return useTotemTip({ content: props.name ?? "" })
    }
    return undefined
  }
  return (
    <div
      ref={setAnchor()}
      class="max-h-full rounded-full bg-white [&>svg]:h-auto [&>svg]:max-w-full"
      style={{ padding: `${props.size ?? 25 / 1000}rem` }}>
      <Show
        when={props.type === "IM" && props.url}
        fallback={
          <_Avatar
            size={props.size}
            // title={props.name}
            name={props.seed}
            variant="marble"
          />
        }>
        <img
          style={{
            width: `${props.size}px`,
          }}
          class="h-auto max-w-full rounded-full"
          src={props.url}
          alt={props.name}
        />
      </Show>
    </div>
  )
}

Avatar.tagName = "t-avatar"
Avatar.propsDefault = {
  size: 50,
  name: "",
  seed: "",
  url: "",
  type: "TD",
  tooltip: false,
}

export default Avatar
