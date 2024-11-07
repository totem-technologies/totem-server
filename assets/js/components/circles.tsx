import { timestampToDateString, timestampToTimeString } from "@/libs/time"
import { createViewportObserver } from "@solid-primitives/intersection-observer"
import { createMediaQuery } from "@solid-primitives/media"
import { Refs } from "@solid-primitives/refs"
import {
  type Accessor,
  For,
  type JSXElement,
  Match,
  type Resource,
  Show,
  Switch,
  createContext,
  createEffect,
  createResource,
  createSignal,
  useContext,
} from "solid-js"
import {
  type CategoryFilterSchema,
  type EventListSchema,
  type FilterOptionsSchema,
  type PagedEventListSchema,
  totemCirclesApiFilterOptions,
  totemCirclesApiListEvents,
} from "../client/index"
import Avatar from "./avatar"
import ErrorBoundary from "./errors"

interface QueryParams extends Record<string, string | number> {
  limit: number
  category: string
  author: string
}

interface DateChunk {
  date: string
  day: number
  month: string
  weekdayShort: string
  events: EventListSchema[]
  dateId: string
}

interface CircleListContextType {
  params: Accessor<QueryParams>
  setParams: (params: QueryParams) => void
  reset: () => void
  refetch: () => void
  events: Resource<PagedEventListSchema | undefined>
  chunkedEvents: () => DateChunk[]
  getMore: () => void
  activeID: Accessor<string>
  setActiveID: (id: string) => void
  scrolling: Accessor<boolean>
  setScrolling: (scrolling: boolean) => void
  setCategory: (category: string) => void
  filters: Resource<FilterOptionsSchema | undefined>
}

const defaultParams: QueryParams = {
  limit: 20,
  category: "",
  author: "",
}

const CircleListContext = createContext<CircleListContextType>()

function CircleListProvider(props: { children: JSXElement }) {
  const [params, setParams] = createSignal<QueryParams>(getQueryParams())
  const [scrolling, setScrolling] = createSignal<boolean>(false)
  const [activeID, setActiveID] = createSignal<string>("")
  createEffect(() => {
    const urlParams = new URLSearchParams()
    let key: keyof QueryParams
    for (key in params()) {
      if (!params()[key]) continue
      urlParams.append(key, params()[key].toString())
    }
    window.history.replaceState(null, "", `?${urlParams.toString()}`)
    void refetch()
  })
  const [events, { refetch }] = createResource(async () => {
    return (await totemCirclesApiListEvents({ query: params() })).data
  })
  const refetch2 = () => {
    void refetch()
  }
  const [filters] = createResource(
    async () => {
      return (await totemCirclesApiFilterOptions({})).data
    },
    {
      initialValue: { categories: [], authors: [] },
    }
  )
  const chunkedEvents = () => {
    const e = events()
    if (!e) return []
    return chunkEventsByDate(e)
  }
  const reset = () => setParams(defaultParams)
  const getMore = () => {
    setParams({
      ...params(),
      limit: params().limit + 10,
    })
  }
  const setCategory = (category: string) => {
    setParams({
      ...params(),
      category: category,
    })
  }
  return (
    <CircleListContext.Provider
      value={{
        params,
        setParams,
        reset,
        refetch: refetch2,
        events,
        chunkedEvents,
        getMore,
        activeID,
        setActiveID,
        scrolling,
        setScrolling,
        setCategory,
        filters,
      }}>
      {props.children}
    </CircleListContext.Provider>
  )
}

function chunkEventsByDate(events: PagedEventListSchema) {
  const dateChunks: DateChunk[] = []
  for (const event of events.items) {
    const start = event.start
    if (!start) {
      console.log("No start date for event", event)
      continue
    }
    const date = timestampToDateString(start)
    const chunk = dateChunks.find((chunk) => chunk.date === date)
    const day = new Date(start).getDate()
    const month = new Date(start).toLocaleDateString("en-US", {
      month: "short",
    })
    const weekdayShort = new Date(start).toLocaleDateString("en-US", {
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
  const urlParams = new URLSearchParams(window.location.search)
  return {
    limit: Number.parseInt(
      urlParams.get("limit") ?? defaultParams.limit.toString()
    ),
    category: urlParams.get("category") ?? defaultParams.category,
    author: urlParams.get("author") ?? defaultParams.author,
  }
}

function Circles(_: { children?: JSXElement }) {
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
  const count = () => {
    return context?.events()?.count ?? 0
  }
  return (
    <Show when={context}>
      <div class="m-auto max-w-7xl">
        <Switch fallback={<div>No Circles yet.</div>}>
          <Match when={context?.events.state === "errored"}>
            <div>Error: {context?.events.error}</div>
          </Match>
          <Match when={context?.events.state === "pending"}>
            <div>Loading...</div>
          </Match>
          <Match when={context?.events()?.count === 0}>
            <div>
              <div>
                No Spaces found. Try resetting the filters, or reloading the
                page.
              </div>
              {/* biome-ignore lint/a11y/useButtonType: <explanation> */}
              <button
                class="btn btn-ghost btn-sm mt-5"
                onClick={context?.reset}>
                Reset
              </button>
            </div>
          </Match>
          <Match when={count() > 0}>
            <QuickFilters />
            <FilterBar />
            <EventsChunkedByDate />
            <Show
              when={
                context?.events()?.items.length === context?.params().limit
              }>
              <button
                type="button"
                class="btn btn-ghost btn-sm mt-5"
                onClick={context?.getMore}>
                More
              </button>
            </Show>
          </Match>
        </Switch>
      </div>
    </Show>
  )
}

function EventsChunkedByDate() {
  const context = useContext(CircleListContext)
  function handleIntersection() {
    // go through elements with chunk.dateIDs and find the one that is closest to the top, absolute value of boundingClientRect.top
    const chunks = context?.chunkedEvents()
    if (!chunks) return
    const closest = chunks.reduce((prev, curr) => {
      let currTop =
        document.getElementById(curr.dateId)?.getBoundingClientRect().top ?? 0
      const prevTop =
        document.getElementById(prev.dateId)?.getBoundingClientRect().top ?? 0
      currTop = currTop < 0 ? currTop - 100 : currTop
      return Math.abs(currTop) <= Math.abs(prevTop) ? curr : prev
    })
    context?.setActiveID(closest.dateId)
  }
  const [intersectionObserver] = createViewportObserver([], handleIntersection)
  return (
    <ul>
      <For each={context?.chunkedEvents()}>
        {(chunk) => (
          <li>
            <div
              use:intersectionObserver={() => handleIntersection()}
              class="invisible relative -top-52 block"
              id={chunk.dateId}
            />
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

function Event(props: { event: EventListSchema }) {
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

function MobileEvent(props: { event: EventListSchema }) {
  const start = () => {
    const s = props.event.start
    if (s) return timestampToTimeString(s)
    return ""
  }
  return (
    <a
      href={props.event.url}
      class="flex items-center justify-center gap-2 border-t-2 p-5 text-left last:border-b-2 hover:bg-white">
      <div class="rounded-full pr-2">{getAvatar(props.event)}</div>
      <div class="grow">
        <Switch>
          <Match when={props.event.title}>
            <p class="font-bold">{props.event.title}</p>
            <p class="text-sm italic">{props.event.space.title}</p>
          </Match>
          <Match when={!props.event.title}>
            <p class="font-bold">{props.event.space.title}</p>
            <Show when={props.event.space.subtitle}>
              <p class="text-sm italic">{props.event.space.subtitle}</p>
            </Show>
          </Match>
        </Switch>
        <p class="text-sm">
          with {getFirstName(props.event.space.author.name ?? "Keeper")} @{" "}
          {start()}
        </p>
      </div>
      <div class="text-2xl">→</div>
    </a>
  )
}

function DesktopEvent(props: { event: EventListSchema }) {
  return (
    <a
      href={props.event.url}
      class="mx-5 mb-2 flex items-center justify-center gap-2 rounded-2xl border-2 border-gray-300 p-5 transition-all hover:bg-white hover:shadow-lg">
      <div>
        <div class="whitespace-nowrap text-lg font-bold">
          {timestampToTimeString(props.event.start ?? "")}
        </div>
      </div>
      <div class="divider divider-horizontal self-stretch" />
      <div class="flex items-center justify-center gap-5">
        <div>{getAvatar(props.event)}</div>
        <div class="text-lg">
          {getFirstName(props.event.space.author.name ?? "Keeper")}
        </div>
      </div>
      <div class="divider divider-horizontal self-stretch" />
      <div class="grow text-center">
        <Switch>
          <Match when={props.event.title}>
            <p class="text-[2vw] font-bold xl:text-2xl">{props.event.title}</p>
            <p class="italic">{props.event.space.title}</p>
          </Match>
          <Match when={!props.event.title}>
            <p class="text-[2vw] font-bold xl:text-2xl">
              {props.event.space.title}
            </p>
            <Show when={props.event.space.subtitle}>
              <p class="italic">{props.event.space.subtitle}</p>
            </Show>
          </Match>
        </Switch>
      </div>
    </a>
  )
}

function getAvatar(event: EventListSchema) {
  return (
    <Avatar
      size={70}
      name={event.space.author.name ?? ""}
      seed={event.space.author.profile_avatar_seed ?? ""}
      url={event.space.author.profile_image ?? undefined}
      type={event.space.author.profile_avatar_type}
    />
  )
}

function FilterBar() {
  const context = useContext(CircleListContext)
  return (
    <Show when={context}>
      <div class="sticky top-0 w-full border-b-2 bg-tcreme px-5 pt-2">
        <div>
          <DateRibbon
            // biome-ignore lint/style/noNonNullAssertion: <explanation>
            chunks={context!.chunkedEvents()}
            // biome-ignore lint/style/noNonNullAssertion: <explanation>
            activeID={context!.activeID()}
          />
        </div>
        <div class="flex w-full items-baseline justify-between p-2">
          <div>
            <FilterModal />
          </div>
          <div>
            <button
              type="button"
              class="btn btn-ghost btn-sm font-normal"
              // biome-ignore lint/style/noNonNullAssertion: <explanation>
              onClick={context!.reset}>
              Reset
            </button>
          </div>
        </div>
      </div>
    </Show>
  )
}

function DateRibbon(props: { chunks: DateChunk[]; activeID: string }) {
  const context = useContext(CircleListContext)
  const [refs, setRefs] = createSignal<HTMLAnchorElement[]>([])
  let scrollableRef: HTMLDivElement
  let containerRef: HTMLDivElement
  createEffect(() => {
    if (context?.scrolling()) return
    // scroll active date into view, dont use scrollIntoView
    const active = refs().find((ref) => ref.dataset.dateid === props.activeID)
    if (active) {
      // avoid scrollIntoView, try to keep the active date in the center
      const centerActive =
        active.getBoundingClientRect().left +
        active.getBoundingClientRect().width / 2
      const containerCenter = containerRef?.getBoundingClientRect().width / 2
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
      context?.setScrolling(false)
    }, 500)
    context?.setScrolling(true)
    document.getElementById(chunkID)?.scrollIntoView({
      behavior: "smooth",
    })
  }

  return (
    <div class="flex justify-center">
      <div class="divider divider-horizontal m-0 ml-1" />
      <div ref={scrollableRef} class="overflow-x-auto overflow-y-hidden">
        <div ref={containerRef} class="flex gap-x-2 px-5 pb-3">
          <Refs ref={setRefs}>
            <For each={props.chunks}>
              {(chunk) => (
                <button
                  type="button"
                  class="cursor-pointer"
                  data-dateid={chunk.dateId}
                  onClick={() => scrollTo(chunk.dateId)}>
                  <h2
                    class={`px-2 text-center transition-all ${classes(chunk)}`}>
                    <div class="text-xs">{chunk.weekdayShort}</div>
                    <div class="text-lg">{chunk.day}</div>
                  </h2>
                </button>
              )}
            </For>
          </Refs>
        </div>
      </div>
      <div class="divider divider-horizontal m-0 mr-1" />
    </div>
  )
}

function FilterModal() {
  const context = useContext(CircleListContext)
  const drawerID = "filter-drawer"
  const selectedCategory = () => context?.params().category
  const selectedAuthor = () => context?.params().author
  return (
    <div class="drawer drawer-end">
      <input id={drawerID} type="checkbox" class="drawer-toggle" />
      <div class="drawer-content">
        <label for={drawerID} class="btn btn-ghost btn-sm font-bold">
          Filters
        </label>
      </div>
      <div class="drawer-side">
        <label
          for={drawerID}
          aria-label="close sidebar"
          class="drawer-overlay"
        />
        <div class="flex min-h-full w-[90vw] max-w-80 flex-col gap-5 bg-tcreme p-4 text-left">
          <h3 class="text-lg font-bold">Filter Circles</h3>
          <div>
            <label class="form-label" for="category">
              Category
            </label>
            <select
              class="form-select"
              id="category"
              onChange={(e) => context?.setCategory(e.currentTarget.value)}>
              <option selected={selectedCategory() === ""} value="">
                All
              </option>
              <For each={context?.filters()?.categories}>
                {(category) => (
                  <option
                    selected={selectedCategory() === category.slug}
                    value={category.slug}>
                    {category.name}
                  </option>
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
                context?.setParams({
                  ...context?.params(),
                  author: e.currentTarget.value,
                })
              }>
              <option selected={selectedAuthor() === ""} value="">
                All
              </option>
              <For each={context?.filters()?.authors}>
                {(author) => (
                  <option
                    selected={selectedAuthor() === author.slug}
                    value={author.slug}>
                    {author.name}
                  </option>
                )}
              </For>
            </select>
          </div>
          <div class="flex justify-between">
            <button
              type="button"
              class="btn btn-ghost btn-sm"
              onClick={context?.reset}>
              Reset
            </button>
            <label
              for={drawerID}
              aria-label="close sidebar"
              class="btn btn-ghost btn-sm">
              Close
            </label>
          </div>
        </div>
      </div>
    </div>
  )
}

function QuickFilters() {
  const context = useContext(CircleListContext)
  const isActive = (category: string) => context?.params().category === category
  const QuickFilterButton = (props: { category: CategoryFilterSchema }) => (
    <button
      type="button"
      class="badge"
      classList={{
        "badge-outline": !isActive(props.category.slug),
        "badge-primary": isActive(props.category.slug),
      }}
      onClick={() => context?.setCategory(props.category.slug)}>
      {props.category.name}
    </button>
  )
  return (
    <div class="m-auto flex max-w-xl flex-wrap items-center justify-center gap-2 px-10 pb-10">
      <QuickFilterButton category={{ name: "All", slug: "" }} />
      <For each={context?.filters()?.categories}>
        {(category) => <QuickFilterButton category={category} />}
      </For>
    </div>
  )
}

Circles.tagName = "t-events-list"
Circles.propsDefault = {}
export default Circles
