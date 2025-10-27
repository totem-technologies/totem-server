import _Avatar from "@totem.org/solid-boring-avatars"
import { type JSXElement, mergeProps, Show } from "solid-js"
import type { ProfileAvatarTypeEnum } from "../client"
import { useTotemTip } from "./tooltip"

const defaults = {
  size: 50,
  name: "",
  seed: "",
  url: "",
  type: "TD",
  tooltip: false,
}

function Avatar(props: {
  size?: number
  name?: string
  seed?: string
  tooltip?: boolean
  url?: string
  type?: ProfileAvatarTypeEnum
  children?: JSXElement
}) {
  const _props = mergeProps(defaults, props)

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
      style={{ padding: `${_props.size / 1000}rem` }}>
      <Show
        when={_props.type === "IM" && _props.url}
        fallback={
          <_Avatar
            size={_props.size}
            // title={_props.name}
            name={_props.seed}
            variant="marble"
          />
        }>
        <img
          style={{
            width: `${_props.size}px`,
          }}
          class="h-auto max-w-full rounded-full"
          src={_props.url}
          alt={_props.name}
        />
      </Show>
    </div>
  )
}

Avatar.tagName = "t-avatar"
Avatar.propsDefault = defaults

export default Avatar
