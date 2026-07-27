import { render } from "@solidjs/testing-library"
import userEvent from "@testing-library/user-event"
import type { ATCBActionEventConfig } from "add-to-calendar-button"
import { beforeAll, beforeEach, expect, test, vi } from "vitest"
import type { SessionDetailSchema } from "../client"
import { EventInfo } from "./detailSidebar"
import { makeSessionDetail } from "./testHelpers"

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
})

const START = new Date("2030-01-01T18:00:00.000Z").getTime()

function makeEvent(
  overrides: Partial<SessionDetailSchema> = {}
): SessionDetailSchema {
  return makeSessionDetail(START, overrides)
}

function renderEventInfo(event: SessionDetailSchema) {
  return render(() => <EventInfo eventStore={event} refetchEvent={() => {}} />)
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
