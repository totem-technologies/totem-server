import { render } from "@solidjs/testing-library"
import userEvent from "@testing-library/user-event"
import type { ATCBActionEventConfig } from "add-to-calendar-button"
import { beforeAll, beforeEach, expect, test, vi } from "vitest"
import type { SessionConflictSchema, SessionDetailSchema } from "../client"
import { EventInfo } from "./detailSidebar"
import { makeSessionDetail } from "./testHelpers"

const postData = vi.fn(() =>
  Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }))
)
vi.mock("@/libs/postData", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/libs/postData")>()),
  postData: (...args: unknown[]) =>
    (postData as (...a: unknown[]) => Promise<Response>)(...args),
}))

const resolveConflicts = vi.fn(
  (..._args: unknown[]): Promise<{ data: unknown; error: unknown }> =>
    Promise.resolve({ data: { attending: true }, error: undefined })
)
vi.mock("../client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../client")>()),
  totemSpacesApiRsvpResolveConflicts: (...args: unknown[]) =>
    (resolveConflicts as (...a: unknown[]) => Promise<unknown>)(...args),
}))

const user = userEvent.setup()
const atcbAction = vi.fn<typeof atcb_action>(() => Promise.resolve(""))

beforeAll(() => {
  globalThis.TOTEM_DATA = {
    debug: false,
    is_authenticated: false,
    reload_on_login: false,
  }
  globalThis.atcb_action = atcbAction
})

beforeEach(() => {
  atcbAction.mockClear()
  postData.mockReset()
  postData.mockResolvedValue(
    new Response(JSON.stringify({ ok: true }), { status: 200 })
  )
  resolveConflicts.mockReset()
  resolveConflicts.mockResolvedValue({
    data: { attending: true },
    error: undefined,
  })
  document.cookie = "csrftoken=test-csrf-token"
})

const START = new Date("2030-01-01T18:00:00.000Z").getTime()
const CONFLICT_HEADING = "You’re already signed up for another session."

function makeEvent(
  overrides: Partial<SessionDetailSchema> = {}
): SessionDetailSchema {
  return makeSessionDetail(START, overrides)
}

function renderEventInfo(
  event: SessionDetailSchema,
  refetchEvent: () => void = () => {}
) {
  return render(() => (
    <EventInfo eventStore={event} refetchEvent={refetchEvent} />
  ))
}

function conflictResponse(
  conflictingSessions: SessionDetailSchema[]
): SessionConflictSchema {
  return {
    message: "This session conflicts with another session",
    conflicting_sessions: conflictingSessions,
  }
}

function calendarButton(result: ReturnType<typeof renderEventInfo>) {
  return result.queryByRole("button", { name: /add to calendar/i })
}

test("shows add-to-calendar button when not attending an open session", () => {
  const result = renderEventInfo(makeEvent({ attending: false }))
  expect(result.getByText("Attend this session")).toBeTruthy()
  expect(calendarButton(result)).toBeTruthy()
})

test("shows add-to-calendar button and give up spot when attending", () => {
  const result = renderEventInfo(makeEvent({ attending: true }))
  expect(result.getByText("Give up spot")).toBeTruthy()
  expect(calendarButton(result)).toBeTruthy()
})

test("does not show add-to-calendar button for an ended session", () => {
  const result = renderEventInfo(makeEvent({ ended: true }))
  expect(calendarButton(result)).toBeNull()
})

test("does not show add-to-calendar button for a cancelled session", () => {
  const result = renderEventInfo(makeEvent({ cancelled: true }))
  expect(calendarButton(result)).toBeNull()
})

test("joinable session invites you in", () => {
  const result = renderEventInfo(
    makeEvent({ joinable: true, join_url: "/spaces/join/test-session/" })
  )
  expect(result.getByText("You can enter this session now.")).toBeTruthy()
})

test("started session links to the space's next session", () => {
  const result = renderEventInfo(
    makeEvent({
      started: true,
      next_session: {
        slug: "next-session",
        start: "2030-01-08T18:00:00.000Z",
        link: "/spaces/session/next-session/",
      },
    })
  )
  const link = result.getByRole("link", { name: /next session/i })
  expect(link.getAttribute("href")).toBe("/spaces/session/next-session/")
})

test("next session button uses the short date so it fits on one line", () => {
  const result = renderEventInfo(
    makeEvent({
      ended: true,
      next_session: {
        slug: "next-session",
        // A Tuesday, so the long format would read "Tuesday, January 8th".
        start: "2030-01-08T18:00:00.000Z",
        link: "/spaces/session/next-session/",
      },
    })
  )
  const link = result.getByRole("link", { name: /next session/i })
  expect(link.textContent).toContain("Tue, Jan 8")
  expect(link.textContent).not.toContain("Tuesday")
})

test("started session without a next session falls back to the spaces list", () => {
  const result = renderEventInfo(makeEvent({ started: true }))
  expect(result.getByText("See upcoming Spaces.")).toBeTruthy()
})

test("full session shows a full notice instead of the attend button", () => {
  const result = renderEventInfo(makeEvent({ seats_left: 0, attending: false }))
  expect(result.queryByText("Attend this session")).toBeNull()
  expect(result.container.textContent).toContain("This session is full")
})

test("attendee of a full session still sees give up spot", () => {
  const result = renderEventInfo(makeEvent({ seats_left: 0, attending: true }))
  expect(result.getByText("Give up spot")).toBeTruthy()
})

test("clicking add-to-calendar opens the provider list with the session details", async () => {
  const result = renderEventInfo(makeEvent())
  await user.click(calendarButton(result)!)
  expect(atcbAction).toHaveBeenCalledOnce()
  const config: ATCBActionEventConfig = atcbAction.mock.calls[0][0]
  expect(config.name).toBe("[Totem] Test Session - Test Space")
  expect(config.location).toBe(
    "https://totem.org/spaces/session/test-session/?r=cal_link"
  )
  expect(config.startDate).toBe("2030-01-01")
  expect(config.options).toEqual(["Apple", "Google", "Outlook.com"])
  // "modal" positions in a dedicated viewport-centered host; "overlay"
  // positions off the trigger's flow position, which breaks inside our
  // centered full-width layout and rendered off-screen on mobile.
  expect(config.listStyle).toBe("modal")
})

test("an RSVP conflict opens the mobile-style session comparison dialog", async () => {
  const conflict = makeEvent({
    slug: "existing-session",
    title: "Existing Session",
    attending: true,
  })
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify(conflictResponse([conflict])), { status: 409 })
  )
  const result = renderEventInfo(
    makeEvent({ slug: "new-session", title: "New Session" })
  )

  await user.click(result.getByRole("button", { name: "Attend this session" }))

  expect(result.getByRole("heading", { name: CONFLICT_HEADING })).toBeTruthy()
  expect(result.container.textContent).toContain(
    "To join New Session, you’ll need to give up your spot in Existing Session."
  )
  expect(result.getByText("Your current session")).toBeTruthy()
  expect(result.getByText("New session")).toBeTruthy()
  const comparison = result.getByTestId("conflict-session-comparison")
  expect(comparison.className).toContain("flex-col")
  expect(comparison.className).toContain("[@media(max-height:700px)]:flex-row")
  expect(comparison.className).not.toContain("md:flex-row")
  const cancel = result.getByRole("button", { name: "Cancel" })
  expect(cancel.className).toContain("btn-outline")
  const switchButton = result.getByRole("button", { name: "Switch Sessions" })
  expect(switchButton.parentElement?.className).toContain("flex-col")
  expect(
    result.getByText(
      "Switching removes you from your current session and saves your seat in the new one right away."
    )
  ).toBeTruthy()
})

test("cancel closes the conflict dialog without changing attendance", async () => {
  const conflict = makeEvent({
    slug: "existing-session",
    title: "Existing Session",
    attending: true,
  })
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify(conflictResponse([conflict])), { status: 409 })
  )
  const result = renderEventInfo(makeEvent({ title: "New Session" }))
  await user.click(result.getByRole("button", { name: "Attend this session" }))

  await user.click(result.getByRole("button", { name: "Cancel" }))

  expect(resolveConflicts).not.toHaveBeenCalled()
  expect(result.queryByRole("heading", { name: CONFLICT_HEADING })).toBeNull()
})

test("switching sessions sends every conflict and completes the RSVP flow", async () => {
  const first = makeEvent({ slug: "first-conflict", title: "First Conflict" })
  const second = makeEvent({
    slug: "second-conflict",
    title: "Second Conflict",
  })
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify(conflictResponse([first, second])), {
      status: 409,
    })
  )
  const refetch = vi.fn()
  const result = renderEventInfo(
    makeEvent({ slug: "new-session", title: "New Session" }),
    refetch
  )
  await user.click(result.getByRole("button", { name: "Attend this session" }))

  await user.click(result.getByRole("button", { name: "Switch Sessions" }))

  expect(resolveConflicts).toHaveBeenCalledWith({
    path: { event_slug: "new-session" },
    body: {
      conflicting_session_slugs: ["first-conflict", "second-conflict"],
    },
    headers: { "X-CSRFToken": "test-csrf-token" },
  })
  expect(refetch).toHaveBeenCalledOnce()
  expect(result.queryByRole("heading", { name: CONFLICT_HEADING })).toBeNull()
})

test("a fresh 409 updates the conflict list and keeps the dialog open", async () => {
  const original = makeEvent({
    slug: "original-conflict",
    title: "Original Conflict",
  })
  const fresh = makeEvent({ slug: "fresh-conflict", title: "Fresh Conflict" })
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify(conflictResponse([original])), { status: 409 })
  )
  resolveConflicts.mockResolvedValueOnce({
    data: undefined,
    error: conflictResponse([original, fresh]),
  })
  const result = renderEventInfo(makeEvent({ title: "New Session" }))
  await user.click(result.getByRole("button", { name: "Attend this session" }))

  await user.click(result.getByRole("button", { name: "Switch Sessions" }))

  expect(result.getByText("Fresh Conflict")).toBeTruthy()
  expect(result.getByRole("heading", { name: CONFLICT_HEADING })).toBeTruthy()
})

test("the switch action is disabled while the resolution request is pending", async () => {
  const conflict = makeEvent({ slug: "existing", title: "Existing Session" })
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify(conflictResponse([conflict])), { status: 409 })
  )
  let finishRequest:
    | ((value: { data: unknown; error: unknown }) => void)
    | undefined
  resolveConflicts.mockReturnValueOnce(
    new Promise((resolve) => {
      finishRequest = resolve
    })
  )
  const result = renderEventInfo(makeEvent({ title: "New Session" }))
  await user.click(result.getByRole("button", { name: "Attend this session" }))

  await user.click(result.getByRole("button", { name: "Switch Sessions" }))

  const switching = result.getByRole("button", { name: "Switching…" })
  expect((switching as HTMLButtonElement).disabled).toBe(true)
  finishRequest?.({ data: { attending: true }, error: undefined })
})

test("a non-conflict resolution failure shows the server message", async () => {
  const conflict = makeEvent({ slug: "existing", title: "Existing Session" })
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify(conflictResponse([conflict])), { status: 409 })
  )
  resolveConflicts.mockResolvedValueOnce({
    data: undefined,
    error: { detail: "There are no spots left" },
  })
  const result = renderEventInfo(makeEvent({ title: "New Session" }))
  await user.click(result.getByRole("button", { name: "Attend this session" }))

  await user.click(result.getByRole("button", { name: "Switch Sessions" }))

  expect(result.getByText("There are no spots left")).toBeTruthy()
  expect(result.getByRole("heading", { name: CONFLICT_HEADING })).toBeTruthy()
})
