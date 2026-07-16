import {
  createMemo,
  createSignal,
  Match,
  onCleanup,
  Show,
  Switch,
} from "solid-js"
import LiveBadge from "./liveBadge"

const MINUTE = 60_000

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "always" })

function relative(ms: number): string {
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

// The join window comes from the server (Session.join_window) as absolute
// times; the join view re-validates, so this only controls when the button
// is revealed.
function SessionCountdown(props: {
  start: string
  joinOpensAt: string
  joinClosesAt: string | null
  endsAt: string
  joinUrl: string
  joinable: boolean
}) {
  const [now, setNow] = createSignal(Date.now())
  const timer = setInterval(() => setNow(Date.now()), 1000)
  onCleanup(() => clearInterval(timer))

  const start = createMemo(() => new Date(props.start).getTime())
  const end = createMemo(() => new Date(props.endsAt).getTime())
  const started = () => now() >= start()
  const ended = () => now() >= end()
  const canJoin = () => {
    if (props.joinClosesAt === null) {
      // Open-ended (LiveKit rejoin): only the server knows the real end, so
      // the scheduled end must not hide the button.
      return props.joinable || now() >= new Date(props.joinOpensAt).getTime()
    }
    if (ended()) return false
    if (props.joinable) return true
    return (
      now() >= new Date(props.joinOpensAt).getTime() &&
      now() <= new Date(props.joinClosesAt).getTime()
    )
  }

  return (
    <div class="flex flex-wrap items-center gap-3">
      <Switch>
        <Match when={ended() && !canJoin()}>
          <span class="text-gray-500">This session has ended.</span>
        </Match>
        <Match when={started()}>
          <LiveBadge />
        </Match>
        <Match when={true}>
          <span class="text-gray-500">Starts {relative(start() - now())}</span>
        </Match>
      </Switch>
      <Show when={canJoin()}>
        <a class="btn btn-primary btn-sm" href={props.joinUrl}>
          Join Now
        </a>
      </Show>
    </div>
  )
}

export default SessionCountdown
