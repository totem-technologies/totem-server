import { render } from "@solidjs/testing-library"
import userEvent from "@testing-library/user-event"
import type { ATCBActionEventConfig } from "add-to-calendar-button"
import { beforeAll, beforeEach, expect, test, vi } from "vitest"
import type { SessionDetailSchema } from "../client"
import { EventInfo } from "./detailSidebar"

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

function makeEvent(
  overrides: Partial<SessionDetailSchema> = {}
): SessionDetailSchema {
  return {
    slug: "test-session",
    title: "Test Session",
    space: {
      author: {
        name: "Test Keeper",
        profile_avatar_type: "TD",
        date_created: "2023-01-01T00:00:00.000Z",
      },
      title: "Test Space",
      slug: "test-space",
      date_created: "2023-01-01T00:00:00.000Z",
      date_modified: "2023-01-01T00:00:00.000Z",
      subtitle: "Test Subtitle",
      categories: [],
      recurring: "Once a week",
    },
    space_title: "Test Space",
    description: "A test session",
    price: 0,
    seats_left: 5,
    duration: 60,
    recurring: "Once a week",
    subscribers: 3,
    start: "2030-01-01T18:00:00.000Z",
    attending: false,
    open: true,
    started: false,
    cancelled: false,
    joinable: false,
    ended: false,
    rsvp_url: "/spaces/rsvp/test-session/",
    join_url: null,
    subscribe_url: "/spaces/subscribe/test-space/",
    cal_link: "https://totem.org/spaces/session/test-session/",
    subscribed: null,
    user_timezone: null,
    meeting_provider: "livekit",
    ...overrides,
  }
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
