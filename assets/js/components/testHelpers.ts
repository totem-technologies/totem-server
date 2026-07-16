// Shared component-test fixtures. Not picked up by vitest (no .test. in the
// filename); import from *.test.tsx files only.
import type { SessionDetailSchema } from "@/client"

export const MINUTE = 60_000
export const HOUR = 60 * MINUTE

// Mirrors the server's join window for a regular attendee of a 60-minute
// session (Session.join_window): joining opens 15 minutes before start and
// closes 10 minutes after.
export function sessionTimes(startMs: number) {
  return {
    start: new Date(startMs).toISOString(),
    join_opens_at: new Date(startMs - 15 * MINUTE).toISOString(),
    join_closes_at: new Date(startMs + 10 * MINUTE).toISOString(),
    ends_at: new Date(startMs + 60 * MINUTE).toISOString(),
  }
}

export function makeSessionDetail(
  startMs: number,
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
    ...sessionTimes(startMs),
    attending: false,
    open: true,
    started: false,
    cancelled: false,
    joinable: false,
    ended: false,
    next_session: null,
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
