import { type JSXElement, Match, mergeProps, Switch } from "solid-js"

type TimeFormat = "short" | "at"

const defaults = {
  time: "",
  format: "short",
  className: "",
}

function Time(props: {
  time?: string
  format?: TimeFormat
  className?: string
  children?: JSXElement
}) {
  const _props = mergeProps(defaults, props)
  const time = () => {
    return new Date(_props.time)
  }
  return (
    <time class={_props.className} dateTime={_props.time}>
      <Switch>
        <Match when={_props.format === "short"}>
          <span>
            {time().toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </Match>
        <Match when={_props.format === "at"}>
          {time().toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          })}
          {" @ "}
          <span>
            {time().toLocaleTimeString(undefined, {
              hour: "numeric",
              minute: "2-digit",
              timeZoneName: "short",
            })}
          </span>
        </Match>
      </Switch>
    </time>
  )
}

Time.tagName = "t-time"
Time.propsDefault = defaults
export default Time
