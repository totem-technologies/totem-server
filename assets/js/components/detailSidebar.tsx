import { postData } from "@/libs/postData"
import { timestampToDateString, timestampToTimeString } from "@/time"
import { createQuery } from "@tanstack/solid-query"
import { createSignal, For, JSX, Match, Show, Switch } from "solid-js"
import { EventDetailSchema, totemCirclesApiEventDetail } from "../client"
import AddToCalendarButton from "./AddToCalendarButton"
import Avatar from "./avatar"
import ErrorBoundary from "./errors"
import Icon, { IconName } from "./icons"
import { useTotemTip } from "./tooltip"

function DetailBox(props: { children: JSX.Element }) {
  return (
    <div class="z-20 mt-5 rounded-2xl border border-gray-200 bg-white p-5 md:top-20 md:w-80">
      {props.children}
    </div>
  )
}

function IconLine(props: {
  children: JSX.Element
  tip: string
  icon: IconName
}) {
  const setAnchor = useTotemTip({ content: props.tip })
  return (
    <div
      ref={setAnchor}
      class="flex cursor-help flex-wrap items-center justify-between gap-x-2 underline decoration-dotted">
      <Icon name={props.icon} />
      {props.children}
    </div>
  )
}

function EventInfo(props: {
  eventStore: EventDetailSchema
  refetchEvent: () => void
}) {
  const [error, setError] = createSignal("")
  let plural = props.eventStore.subscribers > 1 ? "s" : ""
  async function handleAttend(e: Event) {
    if (!props.eventStore.rsvp_url) return
    e.preventDefault()
    let response = await postData(props.eventStore.rsvp_url)
    if (response.ok) {
      props.refetchEvent()
      setError("")
    }
    if (response.status >= 400) {
      setError((await response.json())["error"])
    }
    if (response.redirected) {
      window.location.href = response.url
    }
  }
  async function handleGiveUp(e: Event) {
    if (!props.eventStore.rsvp_url) return
    e.preventDefault()
    await postData(props.eventStore.rsvp_url, { action: "remove" })
    props.refetchEvent()
  }
  return (
    <DetailBox>
      <div class="flex flex-wrap justify-between gap-x-4 gap-y-2 pb-2">
        <Show when={props.eventStore.subscribers}>
          <IconLine
            icon="star"
            tip="How many people are getting updates about this Space.">
            {props.eventStore.subscribers} subscriber{plural}
          </IconLine>
        </Show>
        <IconLine icon="dollar" tip="The cost of each session, if any.">
          <Show when={props.eventStore.price} fallback="No Cost">
            ${props.eventStore.price}
          </Show>
        </IconLine>
        <IconLine icon="clock" tip="How long this session is.">
          {props.eventStore.duration} min
        </IconLine>
        <IconLine
          icon="recur"
          tip="How often this Space generally runs. There may be changes in the schedule due to holidays or other events.">
          {props.eventStore.recurring}
        </IconLine>
        <IconLine
          icon="chair"
          tip="How many people are getting updates about this Space.">
          {props.eventStore.seats_left} seat{plural} left
        </IconLine>
      </div>
      <div class="pb-1 pt-2">
        <strong>{timestampToDateString(props.eventStore.start)}</strong>
        <div>{timestampToTimeString(props.eventStore.start)}</div>
      </div>
      <Show when={error()}>
        <div class="text-red-500">{error()}</div>
      </Show>
      <div class="pt-3 text-center">
        <Switch>
          <Match when={props.eventStore.cancelled}>
            <div>This session has been cancelled.</div>
          </Match>
          <Match when={props.eventStore.joinable}>
            <p class="pb-4">The session is starting now!</p>
            <a
              class="btn btn-primary w-full"
              target="_blank"
              href={props.eventStore.join_url!}>
              Enter Space
            </a>
          </Match>
          <Match when={props.eventStore.ended}>
            <div>This session has ended.</div>
          </Match>
          <Match when={props.eventStore.started}>
            <div>This session has already started.</div>
          </Match>
          <Match when={!props.eventStore.open && !props.eventStore.attending}>
            <div>This session is not open to new participants.</div>
          </Match>

          <Match when={props.eventStore.attending}>
            <AddToCalendarButton
              name={props.eventStore.title}
              calLink={props.eventStore.calLink}
              start={props.eventStore.start}
              durationMinutes={props.eventStore.duration}
            />
            <button class="a pt-2 text-gray-400" onClick={handleGiveUp}>
              Give up spot
            </button>
          </Match>

          <Match when={!props.eventStore.attending}>
            <button
              onClick={handleAttend}
              class="btn btn-primary w-full p-2 px-6">
              Attend this session
            </button>
          </Match>
        </Switch>
      </div>
    </DetailBox>
  )
}

function Attendees(props: { event: EventDetailSchema }) {
  return (
    <Show when={!props.event.ended}>
      <DetailBox>
        <div class="pb-3">
          <strong>Going</strong>
        </div>
        <div class="flex flex-wrap justify-center gap-2">
          <For each={props.event.attendees}>
            {(attendee) => (
              <Avatar
                tooltip={true}
                size={50}
                name={attendee.name || ""}
                seed={attendee.profile_avatar_seed!}
                url={attendee.profile_image!}
                type={attendee.profile_avatar_type}
              />
            )}
          </For>
        </div>
      </DetailBox>
    </Show>
  )
}

function Subscribe(props: {
  event: EventDetailSchema
  refetchEvent: () => void
}) {
  async function handleSubscribe(e: Event) {
    if (!props.event.subscribe_url) return
    e.preventDefault()
    await postData(props.event.subscribe_url, { action: "subscribe" })
    props.refetchEvent()
  }

  async function handleUnubscribe(e: Event) {
    if (!props.event.subscribe_url) return
    e.preventDefault()
    await postData(props.event.subscribe_url, { action: "unsubscribe" })
    props.refetchEvent()
  }

  return (
    <DetailBox>
      <div class="pb-3">
        <strong>Subscribe</strong>
      </div>
      <div class="flex flex-wrap justify-center gap-2">
        <Switch>
          <Match when={props.event.subscribed}>
            <div>You are currently subscribed to this Space.</div>
            <button class="a pt-2 text-gray-400" onClick={handleUnubscribe}>
              Unsubscribe from updates
            </button>
          </Match>
          <Match when={!props.event.subscribed}>
            <div>
              Subscribe to this Space to notified about upcoming sessions.
            </div>
            <button
              class="btn btn-outline w-full p-2 px-6"
              onClick={handleSubscribe}>
              Subscribe
            </button>
          </Match>
        </Switch>
      </div>
    </DetailBox>
  )
}

function Loading() {
  return (
    <DetailBox>
      <div class="text-center">
        <div class="spinner-border" role="status">
          <span class="loading loading-spinner loading-lg"></span>
        </div>
      </div>
    </DetailBox>
  )
}

type DetailSidebarProps = {
  eventid: string
}

function DetailSidebar(props: DetailSidebarProps) {
  if (!props.eventid)
    return (
      <DetailBox>
        <div class="text-center">
          This Space has no upcoming scheduled sessions.
        </div>
      </DetailBox>
    )
  const query = createQuery(() => ({
    queryKey: ["eventData"],
    queryFn: async () => {
      return totemCirclesApiEventDetail({ eventSlug: props.eventid })
    },
    throwOnError: true,
  }))
  return (
    <ErrorBoundary>
      <Switch fallback={<Loading />}>
        <Match when={query.isFetching}>
          <Loading />
        </Match>
        <Match when={query.data}>
          <EventInfo
            eventStore={query.data!}
            refetchEvent={query.refetch}></EventInfo>
          <Show when={query.data?.attending}>
            <Attendees event={query.data!}></Attendees>
          </Show>
          <Show when={query.data?.subscribed !== null}>
            <Subscribe
              event={query.data!}
              refetchEvent={query.refetch}></Subscribe>
          </Show>
        </Match>
      </Switch>
    </ErrorBoundary>
  )
}

DetailSidebar.tagName = "t-detail-sidebar"
DetailSidebar.propsDefault = {
  eventid: "",
}
export default DetailSidebar
