import { createViewportObserver } from "@solid-primitives/intersection-observer"
import { createMediaQuery } from "@solid-primitives/media"
import { Refs } from "@solid-primitives/refs"
import {
  Accessor,
  For,
  Match,
  Resource,
  Show,
  Switch,
  createContext,
  createEffect,
  createResource,
  createSignal,
  useContext,
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
  day: number
  month: string
  events: CircleEventSchema[]
  dateId: string
}

type CircleListContextType = {
  params: Accessor<QueryParams>
  setParams: (params: QueryParams) => void
  reset: () => void
  refetch: () => void
  events: Resource<PagedCircleEventSchema>
  chunkedEvents: () => DateChunk[]
  getMore: () => void
  activeID: Accessor<string>
  setActiveID: (id: string) => void
}

const defaultParams: QueryParams = {
  limit: 20,
  category: "",
}

const CircleListContext = createContext<CircleListContextType>()

function CircleListProvider(props: { children: any }) {
  const [params, setParams] = createSignal<QueryParams>(getQueryParams())
  const [activeID, setActiveID] = createSignal<string>("")
  createEffect(() => {
    const urlParams = new URLSearchParams(params() as any)
    window.history.replaceState(null, "", "?" + urlParams.toString())
    refetch()
  })
  const [events, { refetch }] = createResource(async () => {
    return CirclesService.totemCirclesApiListCircles(params())
  })
  const chunkedEvents = () => {
    if (!events()) return []
    return chunkEventsByDate(events()!)
  }
  const reset = () => setParams(defaultParams)
  const getMore = () => {
    setParams({
      ...params(),
      limit: params().limit + 10,
    })
  }
  return (
    <CircleListContext.Provider
      value={{
        params,
        setParams,
        reset,
        refetch,
        events: events,
        chunkedEvents,
        getMore,
        activeID,
        setActiveID,
      }}>
      {props.children}
    </CircleListContext.Provider>
  )
}

function chunkEventsByDate(events: PagedCircleEventSchema) {
  const dateChunks: DateChunk[] = []
  for (const event of events.items) {
    const date = timestampToDateString(event.start!)
    const chunk = dateChunks.find((chunk) => chunk.date === date)
    const day = new Date(event.start!).getDate()
    const month = new Date(event.start!).toLocaleDateString("en-US", {
      month: "short",
    })
    const dateId = `${month}-${day}`
    if (chunk) {
      chunk.events.push(event)
    } else {
      dateChunks.push({ date, events: [event], dateId, day, month })
    }
  }
  return dateChunks
}

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
  return (
    <CircleListProvider>
      <CirclesInner />
    </CircleListProvider>
  )
}

function CirclesInner() {
  const context = useContext(CircleListContext)
  if (!context) return <div>Loading...</div>
  return (
    <div class="m-auto max-w-7xl">
      <Show when={context.events()} fallback={<div>Loading...</div>}>
        <FilterBar />
        <Switch fallback={<div>No Circles</div>}>
          <Match when={context.events()}>
            <EventsChunkedByDate />
          </Match>
          <Match when={context.events.error}>
            <div>Error: {context.events.error.message}</div>
          </Match>
        </Switch>
      </Show>
      <button onClick={context!.getMore}>More</button>
    </div>
  )
}

function EventsChunkedByDate() {
  const context = useContext(CircleListContext)
  function handleIntersection() {
    // go through elements with chunk.dateIDs and find the one that is closest to the top, absolute value of boundingClientRect.top
    const chunks = context!.chunkedEvents()
    const closest = chunks.reduce((prev, curr) => {
      const currTop = document
        .getElementById(curr.dateId)!
        .getBoundingClientRect().top
      const prevTop = document
        .getElementById(prev.dateId)!
        .getBoundingClientRect().top
      return Math.abs(currTop) < Math.abs(prevTop) ? curr : prev
    })
    context!.setActiveID(closest.dateId)
  }
  const [intersectionObserver] = createViewportObserver([], handleIntersection)
  return (
    <ul>
      <For each={context!.chunkedEvents()}>
        {(chunk) => (
          <li>
            <a
              use:intersectionObserver={(e) => handleIntersection()}
              class="invisible relative -top-52 block"
              id={chunk.dateId}></a>
            <h2 class="h3 p-5 text-left">{chunk.date}</h2>
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

function FilterBar() {
  const context = useContext(CircleListContext)
  return (
    <div class="sticky top-0 w-full border-b-2 bg-tcreme px-5 pt-2">
      <div>
        <DateRibbon
          chunks={context!.chunkedEvents()}
          activeID={context!.activeID()}
        />
      </div>
      <div class="flex w-full items-baseline justify-between p-2">
        <div>
          <button>Filter</button>
        </div>
        <div>
          <button>Sort</button>
        </div>
        <div>
          <button onClick={context!.reset}>Reset</button>
        </div>
      </div>
    </div>
  )
}

function DateRibbon(props: { chunks: DateChunk[]; activeID: string }) {
  const [refs, setRefs] = createSignal<HTMLAnchorElement[]>([])
  let scrollableRef: HTMLDivElement
  let containerRef: HTMLDivElement
  createEffect(() => {
    // scroll active date into view, dont use scrollIntoView
    const active = refs().find((ref) => ref.dataset.dateid === props.activeID)
    if (active) {
      // avoid scrollIntoView, try to keep the active date in the center
      const centerActive =
        active.getBoundingClientRect().left +
        active.getBoundingClientRect().width / 2
      const containerCenter = containerRef.getBoundingClientRect().width / 2
      scrollableRef.scrollTo({
        left:
          Math.abs(containerRef.getBoundingClientRect().left) +
          centerActive -
          containerCenter,
        behavior: "smooth",
      })
    }
  })

  return (
    <div class="flex justify-center">
      <div class="divider divider-horizontal m-0 ml-1 "></div>
      <div ref={scrollableRef!} class="overflow-y-hidden overflow-x-scroll">
        <div ref={containerRef!} class="flex gap-x-5 px-5">
          <Refs ref={setRefs}>
            <For each={props.chunks}>
              {(chunk) => (
                <a data-dateid={chunk.dateId} href={`#${chunk.dateId}`}>
                  <h2
                    class="text-center text-lg font-semibold"
                    style={{
                      color: chunk.dateId === props.activeID ? "blue" : "black",
                    }}>
                    {chunk.month} <br />
                    {chunk.day}
                  </h2>
                </a>
              )}
            </For>
          </Refs>
        </div>
      </div>
      <div class="divider divider-horizontal m-0 mr-1 "></div>
    </div>
  )
}

Circles.tagName = "t-circles"
Circles.propsDefault = {}
export default Circles
