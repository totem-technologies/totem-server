import { useQuery } from "@tanstack/solid-query"
import { createSignal, For, Show, Suspense } from "solid-js"
import { postData } from "@/libs/postData"
import { timestampToDateString, timestampToTimeString } from "@/libs/time"
import { type SpaceDetailSchema, totemSpacesApiSpacesSummary } from "../client"
import Avatar from "./avatar"

export function SpaceCard(props: { space: SpaceDetailSchema }) {
  const next = () => props.space.next_event
  const [optimisticAttending, setOptimisticAttending] = createSignal(false)
  const [error, setError] = createSignal("")
  const attending = () => optimisticAttending() || next()?.attending

  async function handleAttend(e: Event) {
    e.preventDefault()
    const rsvpUrl = next()?.rsvp_url
    if (!rsvpUrl) return
    setError("")
    setOptimisticAttending(true)
    const response = await postData(rsvpUrl)
    if (!response.ok) {
      setOptimisticAttending(false)
      let message = "Could not save your spot. Please try again."
      try {
        message = ((await response.json()) as { error: string }).error
      } catch {
        // keep the default message
      }
      setError(message)
    }
    // On success the optimistic "Attending" pill stays; the summary is not
    // refetched because this space would drop out of the recommendation list,
    // making the card vanish mid-interaction.
  }

  return (
    <li class="col-span-1 list-none overflow-clip rounded-3xl border border-gray-200 bg-white shadow-sm transition-shadow hover:shadow-xl">
      <a href={next()?.link ?? `/spaces/${props.space.slug}/`}>
        <div
          class="relative flex flex-col p-5"
          classList={{ "no-image": !props.space.image_link }}
          style={
            props.space.image_link
              ? {
                  "background-image": `linear-gradient(355deg, rgba(1,1,1,0), rgba(0,0,0,0.6)), url(${props.space.image_link})`,
                  "background-size": "cover",
                  "background-position": "center",
                }
              : {}
          }>
          <div class="flex min-h-[100px] justify-between">
            <div class="self-end">
              <h1 class="h3 pb-2 text-white">{props.space.title}</h1>
              <div class="text-white">with {props.space.author.name}</div>
            </div>
            <div class="min-w-[50px] self-end">
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
            <p class="font-normal text-gray-700">
              {timestampToDateString(next()!.start)}
              <br />
              {timestampToTimeString(next()!.start)}
            </p>
            <Show
              when={!attending()}
              fallback={
                <a class="btn btn-outline btn-sm" href={next()!.link}>
                  ✓ Attending
                </a>
              }>
              <button
                type="button"
                class="btn btn-primary btn-sm px-5"
                onClick={(e) => void handleAttend(e)}>
                Attend
              </button>
            </Show>
          </div>
          <Show when={error()}>
            <div class="pt-2 text-sm text-red-500">{error()}</div>
          </Show>
        </Show>
      </div>
    </li>
  )
}

function ForYou() {
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
  const personalized = () => (query.data?.for_you.length ?? 0) > 0
  const spaces = () => {
    const data = query.data
    if (!data) return []
    const list = personalized() ? data.for_you : data.explore
    return list.slice(0, 4)
  }
  return (
    <div class="pb-5">
      <div class="flex items-baseline justify-between pb-3">
        <strong>
          <h3 id="recommended">
            {personalized() ? "Recommended for You" : "Explore Spaces"}
          </h3>
        </strong>
        <a class="link" href="/spaces/">
          See all Spaces
        </a>
      </div>
      <Suspense
        fallback={
          <div class="p-10 text-center">
            <span class="loading loading-spinner loading-lg" />
          </div>
        }>
        <Show
          when={!query.data || spaces().length > 0}
          fallback={
            <p>
              There are no upcoming Spaces to show you yet. We'll let you know
              when there are new Spaces to join!
            </p>
          }>
          <ul class="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <For each={spaces()}>{(space) => <SpaceCard space={space} />}</For>
          </ul>
        </Show>
      </Suspense>
    </div>
  )
}

ForYou.tagName = "t-for-you"
ForYou.propsDefault = {}

export default ForYou
