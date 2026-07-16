import { render, within } from "@solidjs/testing-library"
import userEvent from "@testing-library/user-event"
import { createSignal } from "solid-js"
import { beforeEach, expect, test, vi } from "vitest"
import type {
  SessionDetailSchema,
  SpaceDetailSchema,
  SummarySpacesSchema,
} from "../client"
import { DashboardView, greeting, groupSessionsByDay } from "./dashboard"
import { HOUR, makeSessionDetail } from "./testHelpers"

const postData = vi.fn(() =>
  Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }))
)
vi.mock("@/libs/postData", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/libs/postData")>()),
  postData: (...args: unknown[]) =>
    (postData as (...a: unknown[]) => Promise<Response>)(...args),
}))

const user = userEvent.setup()

beforeEach(() => {
  postData.mockClear()
})

// A fixed reference time, noon local so day-offsets never cross midnight.
const NOW = new Date(2030, 0, 15, 12, 0, 0)

function isoAt(offsetMs: number) {
  return new Date(NOW.getTime() + offsetMs).toISOString()
}

let slugCounter = 0

function makeSession(
  overrides: Partial<SessionDetailSchema> = {}
): SessionDetailSchema {
  const slug = overrides.slug ?? `session-${++slugCounter}`
  // Lifecycle times follow the (possibly overridden) start.
  const startMs = new Date(overrides.start ?? isoAt(2 * HOUR)).getTime()
  return makeSessionDetail(startMs, {
    slug,
    title: "Weekly Check-in",
    space: {
      author: {
        name: "Keeper Kim",
        profile_avatar_type: "TD",
        date_created: "2023-01-01T00:00:00.000Z",
      },
      title: "Grief Space",
      slug: "grief-space",
      date_created: "2023-01-01T00:00:00.000Z",
      date_modified: "2023-01-01T00:00:00.000Z",
      subtitle: "A space",
      categories: [],
      recurring: "Once a week",
    },
    space_title: "Grief Space",
    description: "desc",
    seats_left: 3,
    subscribers: 2,
    attending: true,
    rsvp_url: `/spaces/rsvp/${slug}/`,
    join_url: `/spaces/join/${slug}/`,
    subscribe_url: "/spaces/subscribe/grief-space/",
    cal_link: `https://totem.org/spaces/session/${slug}/`,
    subscribed: true,
    ...overrides,
  })
}

function makeSpace(
  overrides: Partial<SpaceDetailSchema> = {}
): SpaceDetailSchema {
  return {
    slug: "rec-space",
    title: "Anxiety Space",
    image_link: null,
    short_description: "short",
    content: "<p>content</p>",
    author: {
      name: "Keeper Lee",
      profile_avatar_type: "TD",
      date_created: "2023-01-01T00:00:00.000Z",
    },
    next_event: {
      slug: "rec-session",
      start: isoAt(48 * HOUR),
      ends_at: isoAt(49 * HOUR),
      link: "/spaces/session/rec-session/",
      title: "Intro Session",
      seats_left: 5,
      duration: 60,
      meeting_provider: "livekit",
      cal_link: "https://totem.org/spaces/session/rec-session/",
      rsvp_url: "/spaces/rsvp/rec-session/",
      attending: false,
      cancelled: false,
      open: true,
      joinable: false,
    },
    category: "Anxiety",
    subscribers: 9,
    recurring: "Once a week",
    price: 0,
    ...overrides,
  }
}

function makeSummary(
  overrides: Partial<SummarySpacesSchema> = {}
): SummarySpacesSchema {
  return {
    upcoming: [],
    for_you: [],
    explore: [],
    ...overrides,
  }
}

function renderDashboard(summary: SummarySpacesSchema, refetch = vi.fn()) {
  const result = render(() => (
    <DashboardView name="Sam" summary={summary} refetch={refetch} now={NOW} />
  ))
  return { result, refetch }
}

test("greeting follows the local hour", () => {
  expect(greeting(new Date(2030, 0, 15, 8))).toBe("Good morning")
  expect(greeting(new Date(2030, 0, 15, 11, 59))).toBe("Good morning")
  expect(greeting(new Date(2030, 0, 15, 12))).toBe("Good afternoon")
  expect(greeting(new Date(2030, 0, 15, 17))).toBe("Good evening")
  expect(greeting(new Date(2030, 0, 15, 23))).toBe("Good evening")
})

// --- groupSessionsByDay ---

test("groups sessions into Today, Tomorrow, and dated labels", () => {
  const sessions = [
    makeSession({ start: isoAt(1 * HOUR) }),
    makeSession({ start: isoAt(3 * HOUR) }),
    makeSession({ start: isoAt(25 * HOUR) }),
    makeSession({ start: isoAt(10 * 24 * HOUR) }),
  ]
  const groups = groupSessionsByDay(sessions, NOW)
  expect(groups.map((g) => g.label)).toEqual([
    "Today",
    "Tomorrow",
    new Date(NOW.getTime() + 10 * 24 * HOUR).toLocaleDateString(undefined, {
      weekday: "short",
      month: "long",
      day: "numeric",
    }),
  ])
  expect(groups[0].sessions).toHaveLength(2)
  expect(groups[1].sessions).toHaveLength(1)
})

// --- DashboardView ---

test("renders greeting, hero, day groups, and recommendations", () => {
  const heroSession = makeSession({
    slug: "hero",
    title: "Soonest Session",
    start: isoAt(1 * HOUR),
  })
  const later = makeSession({
    slug: "later",
    title: "Later Session",
    start: isoAt(26 * HOUR),
  })
  const { result } = renderDashboard(
    makeSummary({
      upcoming: [heroSession, later],
      for_you: [makeSpace()],
    })
  )
  // NOW is noon, so the browser-local greeting is afternoon
  expect(result.getByText("Good afternoon, Sam.")).toBeTruthy()
  expect(result.getByText(/signed up for 2 upcoming sessions/)).toBeTruthy()
  const hero = result.getByText("Your next session").closest("section")!
  expect(
    within(hero).getByRole("heading", { name: "Soonest Session" })
  ).toBeTruthy()
  // the hero calendar button must not stretch and push "Give up spot" off the card
  const heroCalendar = within(hero).getByRole("button", {
    name: /add to calendar/i,
  })
  expect(heroCalendar.className).not.toContain("w-full")
  // no overflow-clip ancestor, or the provider dropdown gets cut off at the card edge
  expect(heroCalendar.closest(".overflow-clip")).toBeNull()
  expect(within(hero).getByText("Give up spot")).toBeTruthy()
  // hero session is not repeated in the day groups
  const sessions = result.getByText("My sessions").closest("section")!
  expect(
    within(sessions).queryByRole("heading", { name: "Soonest Session" })
  ).toBeNull()
  expect(
    within(sessions).getByRole("heading", { name: "Later Session" })
  ).toBeTruthy()
  expect(within(sessions).getByText("Tomorrow")).toBeTruthy()
  expect(result.getByText("Recommended for you")).toBeTruthy()
  expect(result.getByText("Anxiety Space")).toBeTruthy()
})

test("welcome empty state when there are no upcoming sessions", () => {
  const { result } = renderDashboard(makeSummary({ explore: [makeSpace()] }))
  expect(result.getByText("Find your people.")).toBeTruthy()
  expect(result.queryByText("Your next session")).toBeNull()
  expect(result.getByText("Explore Spaces", { selector: "h2" })).toBeTruthy()
})

test("space title eyebrow hidden when it matches the session title", () => {
  const { result } = renderDashboard(
    makeSummary({
      upcoming: [
        makeSession({
          title: "",
          space_title: "Grief Space",
          start: isoAt(HOUR),
        }),
      ],
    })
  )
  // only the h3 renders the name; no uppercase eyebrow div duplicate
  expect(result.getAllByText("Grief Space", { selector: "h3" })).toHaveLength(1)
  expect(result.queryByText("Grief Space", { selector: "div" })).toBeNull()
})

test("give up spot confirms, posts, and refetches in place", async () => {
  const { result, refetch } = renderDashboard(
    makeSummary({
      upcoming: [
        makeSession({ slug: "hero", start: isoAt(HOUR) }),
        makeSession({
          slug: "row-1",
          title: "Row Session",
          start: isoAt(30 * HOUR),
        }),
      ],
    })
  )
  const row = result
    .getByRole("heading", { name: "Row Session" })
    .closest("li")!
  await user.click(within(row).getByText("Give up spot"))
  await user.click(within(row).getByRole("button", { name: "Give up my spot" }))
  expect(postData).toHaveBeenCalledWith("/spaces/rsvp/row-1/", {
    action: "remove",
  })
  expect(refetch).toHaveBeenCalledOnce()
})

test("give up spot failure shows the server error and does not refetch", async () => {
  postData.mockResolvedValueOnce(
    new Response(
      JSON.stringify({ error: "This session has already started." }),
      {
        status: 400,
      }
    )
  )
  const { result, refetch } = renderDashboard(
    makeSummary({ upcoming: [makeSession({ start: isoAt(HOUR) })] })
  )
  await user.click(result.getByText("Give up spot"))
  await user.click(result.getByRole("button", { name: "Give up my spot" }))
  expect(result.getByText("This session has already started.")).toBeTruthy()
  expect(refetch).not.toHaveBeenCalled()
})

test("failed attend on a recommendation shows the error and stays attendable", async () => {
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify({ error: "This session is full." }), {
      status: 400,
    })
  )
  const { result, refetch } = renderDashboard(
    makeSummary({ for_you: [makeSpace()] })
  )
  await user.click(result.getByRole("button", { name: "Attend" }))
  expect(result.getByText("This session is full.")).toBeTruthy()
  const attend = result.getByRole("button", { name: "Attend" })
  expect(attend).toBeTruthy()
  expect((attend as HTMLButtonElement).disabled).toBe(false)
  expect(refetch).not.toHaveBeenCalled()
})

test("attending a recommendation updates my sessions and flips the card to give up", async () => {
  const hero = makeSession({ slug: "hero", start: isoAt(HOUR) })
  const recSpace = makeSpace() // next_event: rec-session, rsvp /spaces/rsvp/rec-session/
  const attended = makeSession({
    slug: "rec-session",
    title: "Intro Session",
    space_title: "Anxiety Space",
    start: isoAt(48 * HOUR),
    rsvp_url: "/spaces/rsvp/rec-session/",
  })
  const before = makeSummary({ upcoming: [hero], for_you: [recSpace] })
  const after = makeSummary({ upcoming: [hero, attended], for_you: [] })
  const [summary, setSummary] = createSignal(before)
  // simulate the query refetch: attend -> session appears in upcoming,
  // space drops out of recommendations; give up -> back to the start
  const refetch = vi.fn(() =>
    setSummary((s) => (s === before ? after : before))
  )
  const result = render(() => (
    <DashboardView name="Sam" summary={summary()} refetch={refetch} now={NOW} />
  ))

  await user.click(result.getByRole("button", { name: "Attend" }))
  expect(postData).toHaveBeenCalledWith("/spaces/rsvp/rec-session/")
  expect(refetch).toHaveBeenCalledOnce()

  // the top of the page now shows the new session
  expect(result.getByText(/signed up for 2 upcoming sessions/)).toBeTruthy()
  const sessions = result.getByText("My sessions").closest("section")!
  expect(
    within(sessions).getByRole("heading", { name: "Intro Session" })
  ).toBeTruthy()

  // the card is still there (pinned) and now offers give up instead of attend
  const card = result
    .getByRole("heading", { name: "Anxiety Space" })
    .closest("li")!
  expect(within(card).queryByRole("button", { name: "Attend" })).toBeNull()
  expect(within(card).getByText("Give up spot")).toBeTruthy()

  // giving up from the card reverses everything
  await user.click(within(card).getByText("Give up spot"))
  await user.click(
    within(card).getByRole("button", { name: "Give up my spot" })
  )
  expect(postData).toHaveBeenCalledWith("/spaces/rsvp/rec-session/", {
    action: "remove",
  })
  expect(result.getByText(/signed up for 1 upcoming session\./)).toBeTruthy()
  expect(within(card).getByRole("button", { name: "Attend" })).toBeTruthy()
})

test("started session shows Started instead of give up", () => {
  const { result } = renderDashboard(
    makeSummary({
      upcoming: [makeSession({ started: true, start: isoAt(-1 * HOUR) })],
    })
  )
  expect(result.queryByText("Give up spot")).toBeNull()
  expect(result.getByText("Started")).toBeTruthy()
})
