import { useKeyDownEvent } from "@solid-primitives/keyboard"
import { useQuery } from "@tanstack/solid-query"
import {
  createEffect,
  createSignal,
  type JSX,
  type JSXElement,
  Match,
  Show,
  Suspense,
  Switch,
} from "solid-js"
import { postData } from "@/libs/postData"
import { timestampToDateString, timestampToTimeString } from "@/libs/time"
import { type EventDetailSchema, totemSpacesApiEventDetail } from "../client"
import AddToCalendarButton from "./AddToCalendarButton"
import ErrorBoundary from "./errors"
import Icon, { type IconName } from "./icons"
import { useTotemTip } from "./tooltip"

function capitalize(str: string) {
  return str.charAt(0).toUpperCase() + str.slice(1)
}

const spacesListLink = "/spaces/"

const [showAttendingPopup, setShowAttendingPopup] = createSignal<boolean>(false)
const [showLoginPopup, setShowLoginPopup] = createSignal<boolean>(false)
const [loginRedirectUrl, setLoginRedirectUrl] = createSignal<string>("")

function LoginPopup() {
  createEffect(() => {
    const modal = document.getElementById("login_modal") as HTMLDialogElement
    if (showLoginPopup()) {
      if (modal) {
        modal.showModal()
      }
    } else {
      if (modal) {
        modal.close()
      }
    }
  })
  return (
    <dialog id="login_modal" class="modal">
      <div class="modal-box">
        <Show when={showLoginPopup()}>
          <h3 class="m-auto text-center text-xl font-bold">
            Welcome to Totem! 👋
          </h3>
          <p class="py-2">
            To attend this session, you'll need to sign in or create an account
            first.
          </p>
          <p class="py-2">
            After signing in, you'll be brought back to this page where you can
            finish reserving your spot.
          </p>
          <div class="flex justify-center">
            <div class="modal-action">
              <button
                type="button"
                class="btn btn-primary"
                onClick={() => {
                  const url = loginRedirectUrl()
                  if (url) {
                    window.location.href = url
                  }
                  setShowLoginPopup(false)
                }}>
                Sign in or Create Account
              </button>
            </div>
          </div>
        </Show>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button type="button" onClick={() => setShowLoginPopup(false)}>
          close
        </button>
      </form>
    </dialog>
  )
}

function createCalendarButton(eventStore: EventDetailSchema) {
  return (
    <AddToCalendarButton
      name={`${eventStore.title} - ${eventStore.space_title}`}
      calLink={eventStore.cal_link}
      start={eventStore.start}
      durationMinutes={eventStore.duration}
    />
  )
}

function AttendingPopup(props: { eventStore: EventDetailSchema | undefined }) {
  let modalRef: HTMLDialogElement | undefined // eslint-disable-line no-unassigned-vars
  createEffect(() => {
    if (showAttendingPopup()) {
      modalRef?.showModal()
    } else {
      modalRef?.close()
    }
  })
  return (
    <dialog ref={modalRef} id="attending_modal" class="modal">
      <div class="modal-box">
        <Show when={showAttendingPopup()}>
          <video
            class="m-auto max-w-50"
            src="/static/video/success.webm"
            muted
            playsinline
            autoplay
          />
          <h3 class="m-auto text-center text-xl font-bold">You're going!</h3>
          <p class="py-2">
            <strong>Next step:</strong> Add this session to your calendar so you
            don't miss it!
          </p>
          <Show when={props.eventStore}>
            <div class="flex justify-center pb-2">
              {createCalendarButton(props.eventStore!)}
            </div>
          </Show>
          <p class="py-2 text-sm text-gray-600">
            We'll also send you a notification before the session starts with a
            link to join.
          </p>
          <p class="py-2">
            In the meantime, review our{" "}
            <a
              class="link"
              target="_blank"
              href="https://www.totem.org/guidelines"
              rel="noreferrer">
              Community Guidelines
            </a>{" "}
            to learn more about how to participate.
          </p>
          <div class="flex justify-center">
            <div class="modal-action">
              <form method="dialog">
                <button
                  type="button"
                  class="btn btn-ghost btn-sm"
                  onClick={() => setShowAttendingPopup(false)}>
                  Close
                </button>
              </form>
            </div>
          </div>
        </Show>
      </div>
    </dialog>
  )
}

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
  const setAnchor = () => useTotemTip({ content: props.tip })
  return (
    <div
      ref={setAnchor()}
      class="flex cursor-help flex-wrap items-center justify-between gap-x-2 underline decoration-dotted">
      <Icon name={props.icon} />
      {props.children}
    </div>
  )
}

function plural(number: number) {
  return number > 1 ? "s" : ""
}

function EventInfo(props: {
  eventStore: EventDetailSchema
  refetchEvent: () => void
}) {
  const [error, setError] = createSignal("")
  async function handleAttend(e: Event) {
    if (!props.eventStore.rsvp_url) return
    e.preventDefault()
    const response = await postData(props.eventStore.rsvp_url)
    if (response.redirected) {
      // Store the URL for later use in the login modal
      setLoginRedirectUrl(response.url)
      // Show the login modal instead of redirecting immediately
      setShowLoginPopup(true)
      return
    }
    if (response.ok) {
      props.refetchEvent()
      setShowAttendingPopup(true)
      setError("")
    }
    if (response.status >= 400) {
      // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
      setError((await response.json()).error)
    }
  }
  async function handleGiveUp(e: Event) {
    setShowAttendingPopup(false)
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
            {props.eventStore.subscribers} subscriber
            {plural(props.eventStore.subscribers)}
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
          {capitalize(props.eventStore.recurring)}
        </IconLine>
        <IconLine
          icon="chair"
          tip="How many people are getting updates about this Space.">
          {props.eventStore.seats_left} seat
          {plural(props.eventStore.seats_left)} left
        </IconLine>
      </div>
      <div class="pt-2 pb-1">
        <strong>{timestampToDateString(props.eventStore.start)}</strong>
        <div>{timestampToTimeString(props.eventStore.start)}</div>
      </div>
      <Show when={error()}>
        <div class="text-red-500">{error()}</div>
      </Show>
      <div class="pt-3 text-center">
        <Switch>
          <Match when={props.eventStore.cancelled}>
            <div>
              This session has been cancelled.{" "}
              <a class="link" href={spacesListLink}>
                See upcoming Spaces.
              </a>
            </div>
          </Match>
          <Match when={props.eventStore.joinable}>
            <p class="pb-4">The session is starting now!</p>
            <a
              class="btn btn-primary w-full"
              target="_blank"
              href={props.eventStore.join_url ?? ""}
              rel="noreferrer">
              Enter Space
            </a>
          </Match>
          <Match when={props.eventStore.ended}>
            <div>
              This session has ended.{" "}
              <a class="link" href={spacesListLink}>
                See upcoming Spaces.
              </a>
            </div>
          </Match>
          <Match when={props.eventStore.started}>
            <div>
              This session has already started.{" "}
              <a class="link" href={spacesListLink}>
                See upcoming Spaces.
              </a>
            </div>
          </Match>
          <Match when={!props.eventStore.open && !props.eventStore.attending}>
            <div>
              This session is not open to new participants.{" "}
              <a class="link" href={spacesListLink}>
                See upcoming Spaces.
              </a>
            </div>
          </Match>

          <Match when={props.eventStore.attending}>
            {createCalendarButton(props.eventStore)}
            <button
              type="button"
              class="a pt-2 text-gray-400"
              onClick={(e) => void handleGiveUp(e)}>
              Give up spot
            </button>
          </Match>

          <Match when={!props.eventStore.attending}>
            <button
              type="button"
              onClick={(e) => void handleAttend(e)}
              class="btn btn-primary w-full p-2 px-6">
              Attend this session
            </button>
          </Match>
        </Switch>
      </div>
    </DetailBox>
  )
}

function Subscribe(props: {
  event: EventDetailSchema
  refetchEvent: () => void
}) {
  const subscribe_url = `/spaces/subscribe/${props.event.space.slug}/`
  async function handleSubscribe(e: Event) {
    e.preventDefault()
    await postData(subscribe_url, { action: "subscribe" })
    props.refetchEvent()
  }

  async function handleUnsubscribe(e: Event) {
    e.preventDefault()
    await postData(subscribe_url, { action: "unsubscribe" })
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
            <button
              type="button"
              class="a pt-2 text-gray-400"
              onClick={(e) => void handleUnsubscribe(e)}>
              Unsubscribe from updates
            </button>
          </Match>
          <Match when={!props.event.subscribed}>
            <div>
              Subscribe to this Space to be notified about upcoming sessions.
            </div>
            <button
              type="button"
              class="btn btn-outline w-full p-2 px-6"
              onClick={(e) => void handleSubscribe(e)}>
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
        <div class="spinner-border">
          <span class="loading loading-spinner loading-lg" />
        </div>
      </div>
    </DetailBox>
  )
}

interface DetailSidebarProps {
  eventid?: string
  children?: JSXElement
}

function DetailSidebar(props: DetailSidebarProps) {
  const kEvent = useKeyDownEvent()
  createEffect(() => {
    const e = kEvent()
    if (e?.key === "Escape") {
      setShowLoginPopup(false)
      setShowAttendingPopup(false)
    }
  })
  if (!props.eventid)
    return (
      <DetailBox>
        <div class="text-center">
          This Space has no upcoming scheduled sessions.
        </div>
      </DetailBox>
    )
  const query = useQuery(() => ({
    queryKey: ["eventData"],
    queryFn: async () => {
      const response = await totemSpacesApiEventDetail({
        path: { event_slug: props.eventid || "" },
      })
      if (response.error) {
        throw new Error(response.error as string)
      }
      return response.data
    },
    throwOnError: true,
  }))
  const refetch = () => void query.refetch()
  return (
    <ErrorBoundary>
      <Suspense fallback={<Loading />}>
        <AttendingPopup eventStore={query.data} />
        <LoginPopup />
        <Switch fallback={<Loading />}>
          <Match when={query.isFetching}>
            <Loading />
          </Match>
          <Match when={query.data}>
            {/* biome-ignore lint/style/noNonNullAssertion: <explanation> */}
            <EventInfo eventStore={query.data!} refetchEvent={refetch} />
            <Show when={query.data?.subscribed !== null}>
              {/* biome-ignore lint/style/noNonNullAssertion: <explanation> */}
              <Subscribe event={query.data!} refetchEvent={refetch} />
            </Show>
          </Match>
        </Switch>
      </Suspense>
    </ErrorBoundary>
  )
}

DetailSidebar.tagName = "t-detail-sidebar"
DetailSidebar.propsDefault = {
  eventid: "",
}
export default DetailSidebar
