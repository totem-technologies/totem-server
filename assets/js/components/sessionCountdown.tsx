import { createSignal, Match, onCleanup, Show, Switch } from "solid-js"

const MINUTE = 60_000
// Mirrors Session.can_join server rules for regular attendees; the join view
// re-validates, so this only controls when the button is revealed.
const GRACE_BEFORE = 15 * MINUTE
const GRACE_AFTER = 10 * MINUTE

function relative(ms: number): string {
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "always" })
  const minutes = Math.round(ms / MINUTE)
  if (Math.abs(minutes) >= 48 * 60) {
    return rtf.format(Math.round(minutes / (24 * 60)), "day")
  }
  if (Math.abs(minutes) >= 100) {
    return rtf.format(Math.round(minutes / 60), "hour")
  }
  if (Math.abs(minutes) >= 1) {
    return rtf.format(minutes, "minute")
  }
  return "now"
}

function SessionCountdown(props: {
  start: string
  duration: number | string
  joinurl: string
  joinable: string | boolean
}) {
  const [now, setNow] = createSignal(Date.now())
  const timer = setInterval(() => setNow(Date.now()), 1000)
  onCleanup(() => clearInterval(timer))

  const start = () => new Date(props.start).getTime()
  const end = () => start() + (Number(props.duration) || 60) * MINUTE
  const started = () => now() >= start()
  const ended = () => now() >= end()
  const serverJoinable = () =>
    props.joinable === true || props.joinable === "true"
  const canJoin = () => {
    if (ended()) return false
    if (serverJoinable()) return true
    return now() >= start() - GRACE_BEFORE && now() <= start() + GRACE_AFTER
  }

  return (
    <div class="flex flex-wrap items-center gap-3">
      <Switch>
        <Match when={ended()}>
          <span class="text-gray-500">This session has ended.</span>
        </Match>
        <Match when={started()}>
          <span class="bg-tyellow text-tslate inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-bold">
            <span class="relative flex h-2 w-2">
              <span class="bg-tslate absolute inline-flex h-full w-full animate-ping rounded-full opacity-40" />
              <span class="bg-tslate relative inline-flex h-2 w-2 rounded-full" />
            </span>
            Happening now
          </span>
        </Match>
        <Match when={true}>
          <span class="text-gray-500">Starts {relative(start() - now())}</span>
        </Match>
      </Switch>
      <Show when={canJoin()}>
        <a class="btn btn-primary btn-sm" href={props.joinurl}>
          Join Now
        </a>
      </Show>
    </div>
  )
}

SessionCountdown.tagName = "t-session-countdown"
SessionCountdown.propsDefault = {
  start: "",
  duration: 60,
  joinurl: "",
  joinable: "false",
}

export default SessionCountdown
