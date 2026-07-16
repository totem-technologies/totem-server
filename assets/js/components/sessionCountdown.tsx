import { createMemo, createSignal, Match, onCleanup, Switch } from "solid-js"
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

// The subset of SessionDetailSchema that describes session timing.
export interface SessionTiming {
  start: string
  join_opens_at: string
  join_closes_at?: string | null
  ends_at: string
  joinable: boolean
}

// A ticking clock over the server-provided lifecycle times. The join window
// comes from the server (Session.join_window) as absolute times; the join
// view re-validates, so canJoin only controls when the button is revealed.
export function createSessionClock(session: () => SessionTiming) {
  const [now, setNow] = createSignal(Date.now())
  const timer = setInterval(() => setNow(Date.now()), 1000)
  onCleanup(() => clearInterval(timer))

  const start = createMemo(() => new Date(session().start).getTime())
  const end = createMemo(() => new Date(session().ends_at).getTime())
  const started = () => now() >= start()
  const ended = () => now() >= end()
  const canJoin = () => {
    const s = session()
    if (s.join_closes_at == null) {
      // Open-ended (LiveKit rejoin): only the server knows the real end, so
      // the scheduled end must not hide the button.
      return s.joinable || now() >= new Date(s.join_opens_at).getTime()
    }
    if (ended()) return false
    if (s.joinable) return true
    return (
      now() >= new Date(s.join_opens_at).getTime() &&
      now() <= new Date(s.join_closes_at).getTime()
    )
  }
  return { now, start, started, ended, canJoin }
}

export function EnterSessionButton(props: {
  session: SessionTiming & { join_url?: string | null }
  small?: boolean
}) {
  const clock = createSessionClock(() => props.session)
  return (
    <Switch>
      <Match when={clock.canJoin()}>
        <a
          class="btn btn-primary shrink-0"
          classList={{ "btn-sm": props.small }}
          href={props.session.join_url ?? ""}>
          Enter Session
        </a>
      </Match>
    </Switch>
  )
}

function SessionCountdown(props: { session: SessionTiming }) {
  const clock = createSessionClock(() => props.session)
  return (
    <div class="flex flex-wrap items-center gap-3">
      <Switch>
        <Match when={clock.ended() && !clock.canJoin()}>
          <span class="text-gray-500">This session has ended.</span>
        </Match>
        <Match when={clock.started()}>
          <LiveBadge />
        </Match>
        <Match when={true}>
          <span class="text-gray-500">
            Starts {relative(clock.start() - clock.now())}
          </span>
        </Match>
      </Switch>
    </div>
  )
}

export default SessionCountdown
