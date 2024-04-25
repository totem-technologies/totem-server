import _Avatar from "@totem.org/solid-boring-avatars"
import { Show } from "solid-js"
import { ProfileAvatarTypeEnum } from "../client"

function Avatar(props: {
  size: number
  name: string
  seed: string
  url?: string
  type?: ProfileAvatarTypeEnum
}) {
  return (
    <div
      class=" max-h-full overflow-hidden rounded-full bg-white [&>svg]:h-auto [&>svg]:max-w-full"
      style={{ padding: `${props.size / 1000}rem` }}>
      <Show
        when={props.type === "IM" && props.url}
        fallback={
          <_Avatar
            size={props.size}
            title={props.name}
            name={props.seed}
            variant="marble"
          />
        }>
        <img
          style={{
            width: props.size + "px",
            height: props.size + "px",
          }}
          class="rounded-full"
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
}

export default Avatar
