import { render } from "@solidjs/testing-library"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import type { SessionListSchema } from "@/client"
import { MobileEvent } from "./sessionsList"

const NOW = new Date("2030-01-01T12:00:00.000Z")

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

function makeEvent(
  overrides: Partial<SessionListSchema> = {}
): SessionListSchema {
  return {
    space: {
      title: "Test Space",
      slug: "test-space",
      date_created: "2023-01-01T00:00:00.000Z",
      date_modified: "2023-01-01T00:00:00.000Z",
      author: {
        name: "Test User",
        profile_avatar_type: "TD",
        date_created: "2023-01-01T00:00:00.000Z",
      },
      subtitle: "Test Subtitle",
    },
    url: "https://totem.org",
    start: new Date(NOW.getTime() + 3_600_000).toISOString(),
    ends_at: new Date(NOW.getTime() + 2 * 3_600_000).toISOString(),
    slug: "test-event",
    date_created: "2023-01-01T00:00:00.000Z",
    date_modified: "2023-01-01T00:00:00.000Z",
    title: "Test Event",
    ...overrides,
  }
}

test("renders session card", () => {
  const result = render(() => <MobileEvent event={makeEvent()} />)
  const html = result.container.innerHTML
  expect(html).toContain("Test Space")
  expect(html).toContain("Test Event")
  expect(html).not.toContain("Invalid")
  expect(html).not.toContain("Happening now")
})

test("marks started sessions as happening now", () => {
  const result = render(() => (
    <MobileEvent
      event={makeEvent({
        start: new Date(NOW.getTime() - 60_000).toISOString(),
      })}
    />
  ))
  expect(result.container.innerHTML).toContain("Happening now")
})

test("the live badge turns off after the session ends", () => {
  const result = render(() => (
    <MobileEvent
      event={makeEvent({
        start: new Date(NOW.getTime() - 2 * 3_600_000).toISOString(),
        ends_at: new Date(NOW.getTime() - 3_600_000).toISOString(),
      })}
    />
  ))
  expect(result.container.innerHTML).not.toContain("Happening now")
})
