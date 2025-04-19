import { timestampToDateStringShort, timestampToTimeString } from "@/libs/time"
import { eventCalendarURL } from "@/libs/urls"
import {
  FaRegularCalendar as Calendar,
  FaSolidChevronRight as ChevronRight,
} from "solid-icons/fa"
import { FiClock as Clock } from "solid-icons/fi"
import { TbArmchair } from "solid-icons/tb"
import ErrorBoundary from "./errors"

import { type SpaceDetailSchema, totemCirclesApiListSpaces } from "@/client"
import {
  type Accessor,
  For,
  type JSXElement,
  type Resource,
  Show,
  createContext,
  createEffect,
  createResource,
  createSignal,
  useContext,
} from "solid-js"
import Avatar from "./avatar"

const testCategories = [
  "Technology",
  "Design",
  "Business",
  "Arts",
  "Lifestyle",
  "Science",
  "Health",
  "Sports",
  "Music",
  "Food & Drink",
  "Film",
  "Books",
  "Games",
  "Travel",
  "Hobbies",
  "Social",
  "Other",
]

const ALL = "All"

interface QueryParams extends Record<string, string | number> {
  category: string
}

interface SpacesListContextType {
  params: Accessor<QueryParams>
  setParams: (params: QueryParams) => void
  spaces: Resource<SpaceDetailSchema[]>
  setCategory: (category: string) => void
}

const defaultParams: QueryParams = {
  category: ALL,
}

const SpacesListContext = createContext<SpacesListContextType>()

function getQueryParams(): QueryParams {
  const urlParams = new URLSearchParams(window.location.search)
  return {
    category: urlParams.get("category") ?? defaultParams.category,
  }
}

function SpacesListProvider(props: { children: JSXElement }) {
  const [params, setParams] = createSignal<QueryParams>(getQueryParams())
  createEffect(() => {
    const urlParams = new URLSearchParams()
    let key: keyof QueryParams
    for (key in params()) {
      if (!params()[key]) continue
      urlParams.append(key, params()[key].toString())
    }
    if (params().category === ALL) {
      window.history.replaceState(null, "", "?")
    } else {
      window.history.replaceState(null, "", `?${urlParams.toString()}`)
    }
    void refetch()
  })
  const [spaces, { refetch }] = createResource(async () => {
    return (await totemCirclesApiListSpaces()).data || []
  })
  const setCategory = (category: string) => {
    setParams({
      ...params(),
      category: category,
    })
  }
  return (
    <SpacesListContext.Provider
      value={{
        params,
        setParams,
        spaces,
        setCategory,
      }}>
      {props.children}
    </SpacesListContext.Provider>
  )
}

function SpacesList(_: { children?: JSXElement }) {
  return (
    <ErrorBoundary>
      <SpacesListProvider>
        <SpacesListInner />
      </SpacesListProvider>
    </ErrorBoundary>
  )
}

function SpaceAvatar(props: { author: SpaceDetailSchema["author"] }) {
  return (
    <Avatar
      size={70}
      name={props.author.name ?? undefined}
      seed={props.author.profile_avatar_seed}
      url={props.author.profile_image ?? undefined}
      type={props.author.profile_avatar_type}
    />
  )
}

function SpacesListInner() {
  const context = useContext(SpacesListContext)
  const activeCategory = () => context?.params().category
  const setActiveCategory = context?.setCategory || (() => {})
  const spaces = () => context?.spaces() ?? []
  const categories: Accessor<string[]> = () => {
    let c = spaces().map((space) => space.category)
    c = Array.from(new Set(c)).sort()
    // const c = testCategories
    return [ALL, ...c].filter((c) => c !== null)
  }

  const filteredSpaces = () =>
    activeCategory() === ALL
      ? spaces()
      : spaces().filter((space) => space.category === activeCategory()) || []

  return (
    <Show when={context}>
      <div class="container mx-auto px-2">
        <div class="mb-8">
          <div class="mb-4 flex flex-col items-center justify-between gap-4 md:flex-row">
            <div class="justify-left no-scrollbar flex max-w-full gap-2 overflow-x-scroll rounded-full border border-gray-300 bg-white/90 p-2">
              <For each={categories()}>
                {(category) => (
                  <button
                    type="button"
                    onClick={() => setActiveCategory(category)}
                    class={`btn rounded-full ${
                      activeCategory() === category
                        ? "btn-primary"
                        : "btn-ghost"
                    }`}>
                    {category}
                  </button>
                )}
              </For>
            </div>
            <a class="btn" href={eventCalendarURL}>
              <Calendar class="mr-1 h-4 w-4" />
              All Events
            </a>
          </div>

          <div class="border-gr overflow-hidden rounded-lg border border-gray-300">
            <For each={filteredSpaces()}>
              {(space, index) => (
                <>
                  <a
                    href={`${space.nextEvent.link}`}
                    class="group block bg-white/80 text-left transition-colors hover:bg-white">
                    <div class="p-4 transition-colors md:p-6">
                      <div class="flex flex-col gap-4 md:flex-row md:gap-6">
                        {/* Space Image */}
                        <Show when={space.image_link}>
                          <div class="relative h-32 w-full flex-shrink-0 overflow-hidden rounded-md md:h-28 md:w-48">
                            <img
                              src={space.image_link || ""}
                              alt={space.title}
                              class="h-full w-full object-cover"
                            />
                          </div>
                        </Show>

                        {/* Content */}
                        <div class="flex flex-1 flex-col">
                          <div class="flex flex-col justify-between gap-2 md:flex-row md:items-start">
                            <div>
                              <div class="mb-1 flex items-center gap-2">
                                <h3 class="group-hover:text-primary text-lg font-semibold transition-colors">
                                  {space.title}
                                </h3>
                                <Show when={space.category}>
                                  <span class="badge badge-ghost hidden md:inline-flex">
                                    {space.category}
                                  </span>
                                </Show>
                              </div>

                              {/* Author info */}
                              <div class="mb-2 flex items-center gap-2">
                                <div class="relative h-6 w-6 overflow-hidden rounded-full">
                                  <SpaceAvatar author={space.author} />
                                </div>
                                <span class="text-muted-foreground text-sm">
                                  {space.author.name}
                                </span>
                              </div>
                            </div>

                            {/* Mobile-only category badge */}
                            <Show when={space.category}>
                              <span class="badge badge-ghost mb-5 self-start md:hidden">
                                {space.category}
                              </span>
                            </Show>
                          </div>

                          {/* Description */}
                          <p class="text-muted-foreground mb-3 line-clamp-2 text-sm">
                            {space.description}
                          </p>

                          {/* Next event info */}
                          <div class="mt-auto flex flex-col justify-between md:flex-row md:items-center">
                            <div>
                              <p class="text-sm font-medium">
                                Next event: {space.nextEvent.title}
                              </p>
                              <div class="mt-2 flex gap-4">
                                <div class="text-muted-foreground flex items-center text-xs">
                                  <Calendar class="mr-1 h-3.5 w-3.5" />
                                  {timestampToDateStringShort(
                                    space.nextEvent.start
                                  )}
                                </div>
                                <div class="text-muted-foreground flex items-center text-xs">
                                  <Clock class="mr-1 h-3.5 w-3.5" />
                                  {timestampToTimeString(space.nextEvent.start)}
                                </div>
                                {/* Add seats left info with armchair icon */}
                                <div class="text-muted-foreground flex items-center text-xs">
                                  <TbArmchair class="mr-1 h-3.5 w-3.5" />
                                  <Show
                                    when={space.nextEvent.seats_left > 0}
                                    fallback="Full">
                                    {space.nextEvent.seats_left}{" "}
                                    {space.nextEvent.seats_left === 1
                                      ? "seat"
                                      : "seats"}{" "}
                                    left
                                  </Show>
                                </div>
                              </div>
                            </div>

                            <ChevronRight class="text-muted-foreground group-hover:text-primary hidden h-5 w-5 transition-colors md:block" />
                          </div>
                        </div>
                      </div>
                    </div>
                  </a>
                  {index() < filteredSpaces().length - 1 && (
                    <hr class="border-t border-gray-300" />
                  )}
                </>
              )}
            </For>
          </div>
        </div>
      </div>
    </Show>
  )
}

SpacesList.propsDefault = {}
SpacesList.tagName = "t-spaces-list"
export default SpacesList
