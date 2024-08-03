import { Match, Switch } from "solid-js"

type TimeFormat = "short" | "at"

function Time(props: { time: string; format: TimeFormat; className?: string }) {
  const time = () => {
    return new Date(props.time)
  }
  return (
    <time class={props.className} dateTime={props.time}>
      <Switch>
        <Match when={props.format === "short"}>
          <span>
            {time().toLocaleTimeString(undefined, {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
        </Match>
        <Match when={props.format === "at"}>
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
Time.propsDefault = {
  time: "",
  format: "short",
  className: "",
}
export default Time
