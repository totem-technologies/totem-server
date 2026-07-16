import { useQuery } from "@tanstack/solid-query"
import {
  createMemo,
  createSignal,
  For,
  type JSXElement,
  Show,
  Suspense,
} from "solid-js"
import { postData, postErrorMessage } from "@/libs/postData"
import { timestampToDateString, timestampToTimeString } from "@/libs/time"
import {
  type SessionDetailSchema,
  type SpaceDetailSchema,
  type SummarySpacesSchema,
  totemSpacesApiSpacesSummary,
} from "../client"
import AddToCalendarButton from "./AddToCalendarButton"
import Avatar from "./avatar"
import SessionCountdown, {
  createSessionClock,
  EnterSessionButton,
} from "./sessionCountdown"
import Time from "./time"

export interface SessionDayGroup {
  label: string
  sessions: SessionDetailSchema[]
}

/** Group sessions (assumed sorted by start) by the browser's local day. */
export function groupSessionsByDay(
  sessions: SessionDetailSchema[],
  now: Date = new Date()
): SessionDayGroup[] {
  const dayKey = (d: Date) =>
    `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
  const today = dayKey(now)
  const tomorrow = dayKey(
    new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  )
  const groups: SessionDayGroup[] = []
  for (const session of sessions) {
    const start = new Date(session.start)
    const key = dayKey(start)
    let label: string
    if (key === today) {
      label = "Today"
    } else if (key === tomorrow) {
      label = "Tomorrow"
    } else {
      label = start.toLocaleDateString(undefined, {
        weekday: "short",
        month: "long",
        day: "numeric",
      })
    }
    const last = groups[groups.length - 1]
    if (last && last.label === label) {
      last.sessions.push(session)
    } else {
      groups.push({ label, sessions: [session] })
    }
  }
  return groups
}

export function greeting(now: Date = new Date()): string {
  const hour = now.getHours()
  if (hour < 12) return "Good morning"
  if (hour < 17) return "Good afternoon"
  return "Good evening"
}

function sessionName(session: SessionDetailSchema) {
  return session.title || session.space_title
}

function GiveUpSpot(props: {
  session: SessionDetailSchema
  onDone: () => void
}) {
  let dialogRef: HTMLDialogElement | undefined // eslint-disable-line no-unassigned-vars
  const [error, setError] = createSignal("")
  const [busy, setBusy] = createSignal(false)

  async function giveUp() {
    setBusy(true)
    setError("")
    const response = await postData(props.session.rsvp_url, {
      action: "remove",
    })
    setBusy(false)
    if (!response.ok) {
      setError(
        await postErrorMessage(
          response,
          "Could not give up your spot. Please try again."
        )
      )
      return
    }
    dialogRef?.close()
    props.onDone()
  }

  // Giving up a spot is blocked server-side once the session starts, and the
  // card's status line already says the session is live — show nothing.
  const clock = createSessionClock(() => props.session)
  return (
    <Show when={!clock.started()}>
      <button
        type="button"
        class="btn-quiet shrink-0 text-sm"
        onClick={() => dialogRef?.showModal()}>
        Give up spot
      </button>
      <dialog ref={dialogRef} class="modal">
        <div class="modal-box">
          <h3 class="text-lg font-bold">Give up your spot?</h3>
          <p class="py-4">
            Your spot in <strong>{sessionName(props.session)}</strong> will be
            opened up for someone else. You can always attend again if a spot is
            still open.
          </p>
          <Show when={error()}>
            <p class="pb-2 text-sm text-red-500">{error()}</p>
          </Show>
          <div class="modal-action">
            <form method="dialog">
              <button class="btn">Keep my spot</button>
            </form>
            <button
              type="button"
              class="btn btn-error"
              disabled={busy()}
              onClick={() => void giveUp()}>
              Give up my spot
            </button>
          </div>
        </div>
        <form method="dialog" class="modal-backdrop">
          <button>close</button>
        </form>
      </dialog>
    </Show>
  )
}

// While the session can be joined, the whole cluster gives way to a single
// Enter Session button; a calendar entry is useless once the session started.
function SessionActions(props: {
  session: SessionDetailSchema
  compact?: boolean
  onChange: () => void
}) {
  const clock = createSessionClock(() => props.session)
  return (
    <Show
      when={!clock.canJoin()}
      fallback={
        <EnterSessionButton session={props.session} small={props.compact} />
      }>
      <div class="flex shrink-0 items-center gap-3">
        <Show when={!clock.started()}>
          <AddToCalendarButton
            name={`${sessionName(props.session)} - ${props.session.space_title}`}
            calLink={props.session.cal_link}
            start={props.session.start}
            durationMinutes={props.session.duration}
            variant={props.compact ? "compact" : "inline"}
          />
        </Show>
        <GiveUpSpot session={props.session} onDone={props.onChange} />
      </div>
    </Show>
  )
}

/** The brand image-header style, or undefined to fall back to `.no-image`.
 * ninja serializes FieldFiles as URLs (e.g. /media/...), or null when unset;
 * the shape check guards against a raw storage path regression. */
function bgImageStyle(image: string | null | undefined) {
  if (image && (image.startsWith("http") || image.startsWith("/"))) {
    return {
      "background-image": `linear-gradient(355deg, rgba(1,1,1,0), rgba(0,0,0,0.6)), url(${image})`,
      "background-size": "cover",
      "background-position": "center",
    }
  }
  return undefined
}

function HeroCard(props: {
  session: SessionDetailSchema
  onChange: () => void
}) {
  const keeper = () => props.session.space.author
  const style = createMemo(() => bgImageStyle(props.session.space.image))
  return (
    <section class="rise relative" style={{ "animation-delay": "60ms" }}>
      <div class="bg-tyellow/40 absolute -top-20 -left-32 -z-10 h-80 w-80 rounded-full blur-3xl" />
      <div class="bg-tpink/25 absolute top-16 -right-24 -z-10 h-64 w-64 rounded-full blur-3xl" />
      <h2 class="eyebrow pb-3" id="next-session">
        Your next session
      </h2>
      {/* no overflow-clip here: the calendar dropdown must overflow the card;
          the header rounds its own top corners instead */}
      <div class="border-tslate/10 rounded-4xl border bg-white shadow-[0_24px_60px_-28px_rgba(38,47,55,0.45)] transition-shadow hover:shadow-[0_28px_70px_-28px_rgba(38,47,55,0.6)]">
        <a href={`/spaces/session/${props.session.slug}/`}>
          <div
            class="relative flex flex-col rounded-t-4xl p-6 md:p-10"
            classList={{ "no-image": !style() }}
            style={style()}>
            <div class="flex min-h-42.5 items-end justify-between gap-4">
              <div>
                <Show
                  when={
                    sessionName(props.session) !== props.session.space_title
                  }>
                  <div class="pb-2 text-xs font-bold tracking-[0.18em] text-white/75 uppercase">
                    {props.session.space_title}
                  </div>
                </Show>
                <h3 class="text-3xl leading-tight font-semibold text-white md:text-4xl">
                  {sessionName(props.session)}
                </h3>
                <div class="pt-3 text-white/90">with {keeper().name}</div>
              </div>
              <div class="min-w-12.5 shrink-0">
                <Avatar
                  size={100}
                  name={keeper().name ?? ""}
                  seed={keeper().profile_avatar_seed ?? ""}
                  url={keeper().profile_image ?? ""}
                  type={keeper().profile_avatar_type}
                />
              </div>
            </div>
          </div>
        </a>
        <div class="flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between md:px-8 md:py-6">
          <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
            <strong class="text-tslate">
              <Time time={props.session.start} format="at" />
            </strong>
            <SessionCountdown session={props.session} />
          </div>
          <SessionActions session={props.session} onChange={props.onChange} />
        </div>
      </div>
    </section>
  )
}

function SessionRow(props: {
  session: SessionDetailSchema
  onChange: () => void
}) {
  const keeper = () => props.session.space.author
  return (
    <li class="border-tslate/10 rounded-2xl border bg-white shadow-sm transition-shadow duration-300 hover:shadow-md">
      <div class="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <a
          class="flex min-w-0 flex-1 items-center gap-4"
          href={`/spaces/session/${props.session.slug}/`}>
          <div class="shrink-0">
            <Avatar
              size={48}
              name={keeper().name ?? ""}
              seed={keeper().profile_avatar_seed ?? ""}
              url={keeper().profile_image ?? ""}
              type={keeper().profile_avatar_type}
            />
          </div>
          <div class="min-w-0">
            <Show
              when={sessionName(props.session) !== props.session.space_title}>
              <div class="text-tmauve truncate text-xs font-bold tracking-[0.14em] uppercase">
                {props.session.space_title}
              </div>
            </Show>
            <h3 class="text-tslate truncate text-lg leading-snug font-semibold">
              {sessionName(props.session)}
            </h3>
            <p class="pt-0.5 text-sm text-gray-500">
              {timestampToTimeString(props.session.start)}
              {" · "}
              {props.session.duration} min · with {keeper().name}
            </p>
          </div>
        </a>
        <div class="pl-16 sm:pl-0">
          <SessionActions
            session={props.session}
            compact
            onChange={props.onChange}
          />
        </div>
      </div>
    </li>
  )
}

function SpaceCard(props: { space: SpaceDetailSchema; actions: JSXElement }) {
  const next = () => props.space.next_event
  const style = createMemo(() => bgImageStyle(props.space.image_link))
  return (
    <li class="border-tslate/10 col-span-1 list-none overflow-clip rounded-3xl border bg-white shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg">
      <a href={next()?.link ?? `/spaces/${props.space.slug}/`}>
        <div
          class="relative flex flex-col p-5"
          classList={{ "no-image": !style() }}
          style={style()}>
          <Show when={props.space.category}>
            <span class="text-tslate absolute top-4 left-4 rounded-full bg-white/85 px-3 py-1 text-xs font-bold backdrop-blur-sm">
              {props.space.category}
            </span>
          </Show>
          <div class="flex min-h-30 justify-between gap-3">
            <div class="self-end">
              <h3 class="pb-2 text-2xl leading-snug font-semibold text-white">
                {props.space.title}
              </h3>
              <div class="text-white/90">with {props.space.author.name}</div>
            </div>
            <div class="min-w-12.5 self-end">
              <Avatar
                size={80}
                name={props.space.author.name ?? ""}
                seed={props.space.author.profile_avatar_seed ?? ""}
                url={props.space.author.profile_image ?? ""}
                type={props.space.author.profile_avatar_type}
              />
            </div>
          </div>
        </div>
      </a>
      <div class="p-5">
        <Show when={next()}>
          <div class="flex items-center justify-between gap-2">
            <div>
              <p class="text-tslate font-medium">
                {timestampToDateString(next()!.start)}
              </p>
              <p class="pt-0.5 text-sm text-gray-500">
                {timestampToTimeString(next()!.start)}
                <Show when={next()!.seats_left > 0}>
                  {" "}
                  &middot; {next()!.seats_left} seat
                  {next()!.seats_left === 1 ? "" : "s"} left
                </Show>
              </p>
            </div>
            {props.actions}
          </div>
        </Show>
      </div>
    </li>
  )
}

function RecommendationActions(props: {
  space: SpaceDetailSchema
  attendingSession: SessionDetailSchema | undefined
  onChange: () => void
}) {
  const [busy, setBusy] = createSignal(false)
  const [error, setError] = createSignal("")
  const next = () => props.space.next_event

  async function attend(e: Event) {
    e.preventDefault()
    const rsvpUrl = next()?.rsvp_url
    if (!rsvpUrl) return
    setBusy(true)
    setError("")
    const response = await postData(rsvpUrl)
    if (!response.ok) {
      setBusy(false)
      setError(
        await postErrorMessage(
          response,
          "Could not save your spot. Please try again."
        )
      )
      return
    }
    // stay disabled until the refetched summary flips this card to give-up
    props.onChange()
  }

  return (
    <div class="flex flex-col items-end gap-1">
      <Show
        when={!props.attendingSession}
        fallback={
          <GiveUpSpot
            session={props.attendingSession!}
            onDone={props.onChange}
          />
        }>
        <button
          type="button"
          class="btn btn-primary btn-sm px-5"
          disabled={busy()}
          onClick={(e) => void attend(e)}>
          Attend
        </button>
      </Show>
      <Show when={error()}>
        <span class="text-sm text-red-500">{error()}</span>
      </Show>
    </div>
  )
}

function Welcome() {
  return (
    <section
      class="rise border-tslate/10 relative overflow-clip rounded-4xl border bg-white p-10 text-center shadow-sm md:p-16"
      style={{ "animation-delay": "60ms" }}>
      <div class="from-tmauve to-tpink absolute -top-12 -right-12 h-44 w-44 rounded-full bg-linear-to-br opacity-20" />
      <div class="from-tblue to-tyellow absolute -bottom-16 -left-12 h-52 w-52 rounded-full bg-linear-to-tr opacity-25" />
      <div class="relative z-10">
        <p class="eyebrow pb-4">Welcome to Totem</p>
        <h2 class="text-tslate text-3xl font-semibold md:text-5xl">
          Find your people.
        </h2>
        <p class="m-auto max-w-xl pt-5 pb-9 leading-relaxed text-gray-600">
          You haven't signed up for any sessions yet. Explore our Spaces to find
          a supportive group that fits what you're going through &mdash; every
          session is guided by a trained Keeper.
        </p>
        <a class="btn btn-primary btn-lg px-8" href="/spaces/">
          Explore Spaces
        </a>
      </div>
    </section>
  )
}

const dayLabelClasses: Record<string, string> = {
  Today: "bg-tyellow text-tslate rounded-full px-4 py-1 text-sm font-bold",
  Tomorrow: "bg-tmauve/15 text-tmauve rounded-full px-4 py-1 text-sm font-bold",
  other: "text-tslate text-lg font-semibold",
}

/** Presentational dashboard: pure function of the summary data. */
export function DashboardView(props: {
  name: string
  summary: SummarySpacesSchema
  refetch: () => void
  now?: Date
}) {
  const upcoming = () => props.summary.upcoming
  const hero = () => upcoming()[0]
  const groups = createMemo(() =>
    groupSessionsByDay(upcoming().slice(1), props.now ?? new Date())
  )

  // Recommendations are captured from the first summary and stay fixed for the
  // visit: attend/give-up refetches change the server's list (attended spaces
  // drop out, others shuffle in), which would move or vanish cards
  // mid-interaction. Each card still derives its Attend/Give-up state live
  // from `upcoming`.
  // eslint-disable-next-line solid/reactivity -- deliberate one-time capture
  const firstSummary = props.summary
  const personalized = firstSummary.for_you.length > 0
  const recommended = (
    personalized ? firstSummary.for_you : firstSummary.explore
  ).slice(0, 4)
  // The registered session backing a recommendation card, if any.
  const attendingSessionFor = (space: SpaceDetailSchema) =>
    upcoming().find((s) => s.slug === space.next_event?.slug)

  return (
    <div>
      <header class="rise pt-14 pb-12">
        <p class="eyebrow pb-3">My Home</p>
        <h1 class="text-tslate text-4xl leading-tight font-semibold md:text-5xl">
          {greeting(props.now)}, {props.name}.
        </h1>
        <Show when={upcoming().length > 0}>
          <p class="pt-4 text-gray-500">
            You're signed up for {upcoming().length} upcoming session
            {upcoming().length === 1 ? "" : "s"}.
          </p>
        </Show>
      </header>
      <Show when={hero()} fallback={<Welcome />}>
        <HeroCard session={hero()} onChange={props.refetch} />
        <Show when={groups().length > 0}>
          <section class="rise pt-14" style={{ "animation-delay": "120ms" }}>
            <h2 class="eyebrow pb-1" id="upcoming">
              My sessions
            </h2>
            <For each={groups()}>
              {(group) => (
                <>
                  <div class="flex items-center gap-4 pt-6 pb-4">
                    <span
                      class={
                        dayLabelClasses[group.label] ?? dayLabelClasses.other
                      }>
                      {group.label}
                    </span>
                    <div class="bg-tslate/10 h-px flex-1" />
                  </div>
                  <ul role="list" class="flex flex-col gap-3">
                    <For each={group.sessions}>
                      {(session) => (
                        <SessionRow
                          session={session}
                          onChange={props.refetch}
                        />
                      )}
                    </For>
                  </ul>
                </>
              )}
            </For>
          </section>
        </Show>
      </Show>
      <div class="rise pt-14" style={{ "animation-delay": "180ms" }}>
        <div class="flex items-baseline justify-between pb-4">
          <h2 class="eyebrow" id="recommended">
            {personalized ? "Recommended for you" : "Explore Spaces"}
          </h2>
          <a
            class="text-tmauve text-sm underline decoration-dotted underline-offset-4 hover:decoration-solid"
            href="/spaces/">
            See all Spaces
          </a>
        </div>
        <Show
          when={recommended.length > 0}
          fallback={
            <p>
              There are no upcoming Spaces to show you yet. We'll let you know
              when there are new Spaces to join!
            </p>
          }>
          <ul class="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <For each={recommended}>
              {(space) => (
                <SpaceCard
                  space={space}
                  actions={
                    <RecommendationActions
                      space={space}
                      attendingSession={attendingSessionFor(space)}
                      onChange={props.refetch}
                    />
                  }
                />
              )}
            </For>
          </ul>
        </Show>
      </div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div class="pt-14">
      <div class="skeleton mb-4 h-4 w-24 rounded-full" />
      <div class="skeleton mb-12 h-12 w-80 rounded-full" />
      <div class="skeleton h-72 w-full rounded-4xl" />
    </div>
  )
}

/** Container: fetches the summary and renders the view. */
function Dashboard(props: { name?: string }) {
  const query = useQuery(() => ({
    queryKey: ["spacesSummary"],
    queryFn: async () => {
      const response = await totemSpacesApiSpacesSummary()
      if (response.error) {
        throw new Error(String(response.error))
      }
      return response.data
    },
    throwOnError: true,
  }))
  return (
    <Suspense fallback={<LoadingSkeleton />}>
      <Show when={query.data}>
        <DashboardView
          name={props.name || "friend"}
          summary={query.data!}
          refetch={() => void query.refetch()}
        />
      </Show>
    </Suspense>
  )
}

Dashboard.tagName = "t-dashboard"
Dashboard.propsDefault = {
  name: "",
}

export default Dashboard
