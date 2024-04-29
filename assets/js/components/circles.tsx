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
  FilterOptionsSchema,
  PagedCircleEventSchema,
} from "../client/index"
import Avatar from "./avatar"
import ErrorBoundary from "./errors"

type QueryParams = {
  limit: number
  category: string
  author: string
}

type DateChunk = {
  date: string
  day: number
  month: string
  weekdayShort: string
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
  scrolling: Accessor<boolean>
  setScrolling: (scrolling: boolean) => void
  filters: Resource<FilterOptionsSchema>
}

const defaultParams: QueryParams = {
  limit: 20,
  category: "",
  author: "",
}

const CircleListContext = createContext<CircleListContextType>()

function CircleListProvider(props: { children: any }) {
  const [params, setParams] = createSignal<QueryParams>(getQueryParams())
  const [scrolling, setScrolling] = createSignal<boolean>(false)
  const [activeID, setActiveID] = createSignal<string>("")
  createEffect(() => {
    const urlParams = new URLSearchParams(params() as any)
    // remove empty params
    for (const key in params()) {
      if (!params()[key as keyof QueryParams]) urlParams.delete(key)
    }
    window.history.replaceState(null, "", "?" + urlParams.toString())
    refetch()
  })
  const [events, { refetch }] = createResource(async () => {
    return CirclesService.totemCirclesApiListCircles(params())
  })
  const [filters, { refetch: filterRefetch }] = createResource(
    async () => {
      return CirclesService.totemCirclesApiFilterOptions()
    },
    {
      initialValue: { categories: [], authors: [] },
    }
  )
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
        events,
        chunkedEvents,
        getMore,
        activeID,
        setActiveID,
        scrolling,
        setScrolling,
        filters,
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
    const weekdayShort = new Date(event.start!).toLocaleDateString("en-US", {
      weekday: "short",
    })
    const dateId = `${month}-${day}`
    if (chunk) {
      chunk.events.push(event)
    } else {
      dateChunks.push({
        date,
        events: [event],
        dateId,
        day,
        month,
        weekdayShort,
      })
    }
  }
  return dateChunks
}

function getFirstName(name: string) {
  return name.split(" ")[0]
}

function getQueryParams(): QueryParams {
  var urlParams = new URLSearchParams(window.location.search)
  return {
    limit: parseInt(urlParams.get("limit") || defaultParams.limit.toString()),
    category: urlParams.get("category") || defaultParams.category,
    author: urlParams.get("author") || defaultParams.author,
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
    <ErrorBoundary>
      <CircleListProvider>
        <CirclesInner />
      </CircleListProvider>
    </ErrorBoundary>
  )
}

function CirclesInner() {
  const context = useContext(CircleListContext)
  if (!context) return <div>Loading...</div>
  return (
    <div class="m-auto max-w-7xl">
      <Switch fallback={<div>No Circles yet.</div>}>
        <Match when={context.events()}>
          <FilterBar />
          <EventsChunkedByDate />
          <Show when={context.events()!.items.length == context.params().limit}>
            <button
              class="btn btn-ghost btn-sm mt-5"
              onClick={context!.getMore}>
              More
            </button>
          </Show>
        </Match>
        <Match when={context.events.error}>
          <div>Error: {context.events.error.message}</div>
        </Match>
        <Match when={context.events.loading}>
          <div>Loading...</div>
        </Match>
      </Switch>
    </div>
  )
}

function EventsChunkedByDate() {
  const context = useContext(CircleListContext)
  function handleIntersection() {
    // go through elements with chunk.dateIDs and find the one that is closest to the top, absolute value of boundingClientRect.top
    const chunks = context!.chunkedEvents()
    const closest = chunks.reduce((prev, curr) => {
      let currTop = document
        .getElementById(curr.dateId)!
        .getBoundingClientRect().top
      let prevTop = document
        .getElementById(prev.dateId)!
        .getBoundingClientRect().top
      currTop = currTop < 0 ? currTop - 100 : currTop
      return Math.abs(currTop) <= Math.abs(prevTop) ? curr : prev
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
      class="flex items-center justify-center gap-2 border-t-2 p-5 text-left hover:bg-white">
      <div class="rounded-full pr-2">{getAvatar(props.event)}</div>

      <div class="flex-grow">
        <p class="font-bold">{props.event.circle.title}</p>
        <p class="text-sm">
          with {getFirstName(props.event.circle.author.name!)}
        </p>
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
        <div class="text-lg">
          {getFirstName(props.event.circle.author.name!)}
        </div>
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
      url={event.circle.author.profile_image || undefined}
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
          <FilterModal />
        </div>
        <div>
          <button
            class="btn btn-ghost btn-sm font-normal"
            onClick={context!.reset}>
            Reset
          </button>
        </div>
      </div>
    </div>
  )
}

function DateRibbon(props: { chunks: DateChunk[]; activeID: string }) {
  const context = useContext(CircleListContext)
  const [refs, setRefs] = createSignal<HTMLAnchorElement[]>([])
  let scrollableRef: HTMLDivElement
  let containerRef: HTMLDivElement
  createEffect(() => {
    if (context!.scrolling()) return
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
  const isActive = (chunk: DateChunk) => chunk.dateId === props.activeID
  const activeClasses =
    "bg-white rounded border-t-4 border-tmauve pt-0 font-semibold shadow-md"
  const inactiveClasses = "text-gray-500 pt-1 hover:bg-white rounded"
  const classes = (chunk: DateChunk) =>
    isActive(chunk) ? activeClasses : inactiveClasses

  const scrollTo = (chunkID: string) => {
    setTimeout(() => {
      context!.setScrolling(false)
    }, 500)
    context!.setScrolling(true)
    document.getElementById(chunkID)!.scrollIntoView({
      behavior: "smooth",
    })
  }

  return (
    <div class="flex justify-center">
      <div class="divider divider-horizontal m-0 ml-1 "></div>
      <div ref={scrollableRef!} class="overflow-x-auto overflow-y-hidden">
        <div ref={containerRef!} class="flex gap-x-2 px-5 pb-3">
          <Refs ref={setRefs}>
            <For each={props.chunks}>
              {(chunk) => (
                <a
                  class="cursor-pointer"
                  data-dateid={chunk.dateId}
                  onClick={() => scrollTo(chunk.dateId)}>
                  <h2
                    class={`px-2 text-center transition-all ${classes(chunk)}`}>
                    <div class="text-xs">{chunk.weekdayShort}</div>
                    <div class="text-lg">{chunk.day}</div>
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

function FilterModal() {
  const context = useContext(CircleListContext)
  return (
    <div class="drawer drawer-end">
      <input id="filter-drawer" type="checkbox" class="drawer-toggle" />
      <div class="drawer-content">
        <label for="filter-drawer" class="btn btn-ghost btn-sm font-bold">
          Filter
        </label>
      </div>
      <div class="drawer-side">
        <label
          for="filter-drawer"
          aria-label="close sidebar"
          class="drawer-overlay"></label>
        <div class="flex min-h-full w-80 flex-col gap-5 bg-tcreme p-4 text-left">
          <h3 class="text-lg font-bold">Filter Circles</h3>
          <div>
            <label class="form-label" for="category">
              Category
            </label>
            <select
              class="form-select"
              id="category"
              onChange={(e) =>
                context!.setParams({
                  ...context!.params(),
                  category: e.currentTarget.value,
                })
              }>
              <option value="">All</option>
              <For each={context!.filters()!.categories}>
                {(category) => (
                  <option value={category.slug}>{category.name}</option>
                )}
              </For>
            </select>
          </div>
          <div>
            <label class="form-label" for="author">
              Keeper
            </label>
            <select
              class="form-select"
              id="author"
              onChange={(e) =>
                context!.setParams({
                  ...context!.params(),
                  author: e.currentTarget.value,
                })
              }>
              <option value="">All</option>
              <For each={context!.filters()!.authors}>
                {(author) => <option value={author.slug}>{author.name}</option>}
              </For>
            </select>
          </div>
        </div>
      </div>
    </div>
  )
}

Circles.tagName = "t-circles"
Circles.propsDefault = {}
export default Circles
