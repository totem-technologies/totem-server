import { createMediaQuery } from "@solid-primitives/media"
import {
  For,
  Match,
  Show,
  Switch,
  createEffect,
  createResource,
  createSignal,
} from "solid-js"
import {
  CircleEventSchema,
  CirclesService,
  PagedCircleEventSchema,
} from "../client/index"
import Avatar from "./avatar"

type QueryParams = {
  limit: number
  category: string
}

type DateChunk = {
  date: string
  events: CircleEventSchema[]
  dateId: string
}

const defaultParams: QueryParams = {
  limit: 20,
  category: "",
}

// const CircleListContext = createContext<QueryParams>(defaultParams)

function getQueryParams(): QueryParams {
  var urlParams = new URLSearchParams(window.location.search)
  return {
    limit: parseInt(urlParams.get("limit") || defaultParams.limit.toString()),
    category: urlParams.get("category") || defaultParams.category,
  }
}

const nthNumber = (number: number) => {
  if (number > 3 && number < 21) return "th"
  switch (number % 10) {
    case 1:
      return "st"
    case 2:
      return "nd"
    case 3:
      return "rd"
    default:
      return "th"
  }
}

function timestampToDateString(timestamp: string) {
  // Date in the form of "Tuesday, May 1st"
  const date = new Date(timestamp).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  })
  return date + nthNumber(new Date(timestamp).getDate())
}

function timestampToTimeString(timestamp: string) {
  // Convert timestamp to HH:MM AM/PM Timezone
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "numeric",
    timeZoneName: "short",
  })
}

function Circles() {
  const [params, setParams] = createSignal<QueryParams>(getQueryParams())
  createEffect(() => {
    const urlParams = new URLSearchParams(params() as any)
    window.history.replaceState(null, "", "?" + urlParams.toString())
    refetch()
  })
  const reset = () => setParams(defaultParams)
  const [events, { mutate, refetch }] = createResource(async () => {
    return CirclesService.totemCirclesApiListCircles(params())
  })
  return (
    <div class="m-auto max-w-7xl">
      <FilterBar events={events()!} onRefetch={refetch} onReset={reset} />
      <Show when={events()} fallback={<div>Loading...</div>}>
        <Switch fallback={<div>No Circles</div>}>
          <Match when={events()}>
            <EventsChunkedByDate events={events()!} />
          </Match>
          <Match when={events.error}>
            <div>Error: {events.error.message}</div>
          </Match>
        </Switch>
      </Show>
      <button
        onClick={() => setParams({ ...params(), limit: params().limit + 10 })}>
        More
      </button>
    </div>
  )
}

function chunkEventsByDate(events: PagedCircleEventSchema) {
  const dateChunks: DateChunk[] = []
  for (const event of events.items) {
    const date = timestampToDateString(event.start!)
    const dateId = date.replace(/[^A-Za-z0-9]/g, "").toLowerCase()
    const chunk = dateChunks.find((chunk) => chunk.date === date)
    if (chunk) {
      chunk.events.push(event)
    } else {
      dateChunks.push({ date, events: [event], dateId })
    }
  }
  return dateChunks
}

function EventsChunkedByDate(props: { events: PagedCircleEventSchema }) {
  const eventsByDate = () => {
    return chunkEventsByDate(props.events)
  }
  return (
    <ul>
      <For each={eventsByDate()}>
        {(chunk) => (
          <li>
            <h2 id={chunk.dateId} class="h3 p-5 text-left">
              {chunk.date}
            </h2>
            <ul>
              <For each={chunk.events}>
                {(event) => <Event event={event} />}
              </For>
            </ul>
          </li>
        )}
      </For>
    </ul>
  )
}

function Event(props: { event: CircleEventSchema }) {
  const isSmall = createMediaQuery("(max-width: 767px)")
  return (
    <>
      <Show when={isSmall()}>
        <MobileEvent event={props.event} />
      </Show>
      <Show when={!isSmall()}>
        <DesktopEvent event={props.event} />
      </Show>
    </>
  )
}

function MobileEvent(props: { event: CircleEventSchema }) {
  return (
    <a
      href={props.event.url}
      class="flex items-center justify-center gap-5 border-t-2 p-5 text-left hover:bg-white">
      <div class="rounded-full bg-white p-[0.2rem]">
        {getAvatar(props.event)}
      </div>

      <div class="flex-grow">
        <p class="font-bold">{props.event.circle.title}</p>
        <p class="text-sm">with {props.event.circle.author.name}</p>
        <p class="text-sm">{timestampToTimeString(props.event.start!)}</p>
      </div>
      <div class="text-2xl">→</div>
    </a>
  )
}

function DesktopEvent(props: { event: CircleEventSchema }) {
  return (
    <a
      href={props.event.url}
      class="mx-5 mb-2 flex items-center justify-center gap-2 rounded-2xl border-2 border-gray-300 p-5 transition-all hover:bg-white hover:shadow-lg">
      <div>
        <div class="whitespace-nowrap text-lg font-bold">
          {timestampToTimeString(props.event.start!)}
        </div>
      </div>
      <div class="divider divider-horizontal self-stretch"></div>
      <div class="flex items-center justify-center gap-5">
        <div>{getAvatar(props.event)}</div>
        <div class="text-lg">{props.event.circle.author.name}</div>
      </div>
      <div class="divider divider-horizontal self-stretch"></div>
      <div class="flex-grow text-center">
        <p class="text-[2vw] font-bold xl:text-2xl">
          {props.event.circle.title}
        </p>
      </div>
    </a>
  )
}

function getAvatar(event: CircleEventSchema) {
  return (
    <Avatar
      size={70}
      name={event.circle.author.name || ""}
      seed={event.circle.author.profile_avatar_seed || ""}
      type={event.circle.author.profile_avatar_type}
    />
  )
}

function FilterBar(props: {
  events: PagedCircleEventSchema
  onRefetch: () => void
  onReset: () => void
}) {
  return (
    <div class="sticky top-0 flex h-20 items-center justify-between border-b-2 bg-tcreme">
      <div>
        <button>Filter</button>
      </div>
      <div>
        <button>Sort</button>
      </div>
      <div>
        <button onClick={props.onRefetch}>Refresh</button>
        <button onClick={props.onReset}>Reset</button>
      </div>
    </div>
  )
}

Circles.tagName = "t-circles"
Circles.propsDefault = {}
export default Circles
