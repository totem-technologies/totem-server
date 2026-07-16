import { render } from "@solidjs/testing-library"
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import type { SessionDetailSchema } from "../client"
import DetailSidebar, { nextTransitionDelay } from "./detailSidebar"
import { makeSessionDetail, MINUTE } from "./testHelpers"

const NOW = new Date("2030-01-01T12:00:00.000Z")

function iso(offsetMs: number) {
  return new Date(NOW.getTime() + offsetMs).toISOString()
}

beforeEach(() => {
  globalThis.TOTEM_DATA = {
    debug: false,
    is_authenticated: false,
    reload_on_login: false,
  }
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

// --- nextTransitionDelay: when is the next server-side state change? ---

test("waits for the next upcoming boundary, plus clock-skew buffer", () => {
  const delay = nextTransitionDelay(
    [iso(-5 * MINUTE), iso(5 * MINUTE), iso(20 * MINUTE)],
    NOW.getTime()
  )
  expect(delay).toBe(5 * MINUTE + 15_000)
})

test("ignores null boundaries (e.g. an open-ended join window)", () => {
  const delay = nextTransitionDelay([null, iso(3 * MINUTE)], NOW.getTime())
  expect(delay).toBe(3 * MINUTE + 15_000)
})

test("nothing to wait for once every boundary has passed", () => {
  expect(
    nextTransitionDelay([iso(-2 * MINUTE), null], NOW.getTime())
  ).toBeNull()
})

test("a just-passed boundary gets one follow-up for fast local clocks", () => {
  // 30s past the boundary: schedule a retry at boundary+60s (+buffer), in
  // case our clock beat the server's and the first refetch was too early.
  const delay = nextTransitionDelay([iso(-30_000)], NOW.getTime())
  expect(delay).toBe(30_000 + 15_000)
})

test("far-future sessions re-check at most daily", () => {
  const delay = nextTransitionDelay([iso(30 * 24 * 60 * MINUTE)], NOW.getTime())
  expect(delay).toBe(24 * 60 * MINUTE)
})

// --- wiring: DetailSidebar refetches when a boundary passes ---

const apiEventDetail = vi.fn()
vi.mock("../client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../client")>()),
  totemSpacesApiEventDetail: (...args: unknown[]) =>
    (apiEventDetail as (...a: unknown[]) => unknown)(...args),
}))

function makeEvent(startOffsetMs: number): SessionDetailSchema {
  return makeSessionDetail(NOW.getTime() + startOffsetMs)
}

test("refetches when the join window opens, even if the data is unchanged", async () => {
  apiEventDetail.mockClear()
  // Session starts in 20 minutes: the next boundary is join_opens_at.
  apiEventDetail.mockImplementation(() =>
    Promise.resolve({ data: makeEvent(20 * MINUTE), error: undefined })
  )
  render(() => (
    <QueryClientProvider client={new QueryClient({})}>
      <DetailSidebar eventid="test-session" />
    </QueryClientProvider>
  ))
  await vi.advanceTimersByTimeAsync(0)
  expect(apiEventDetail).toHaveBeenCalledTimes(1)

  // Identical payload: a second fetch must still be scheduled after this one.
  // join_opens_at is at +5min; the refetch fires at +5:15.
  await vi.advanceTimersByTimeAsync(6 * MINUTE)
  expect(apiEventDetail).toHaveBeenCalledTimes(2)
  // One clock-skew follow-up lands at ~+6:15.
  await vi.advanceTimersByTimeAsync(1 * MINUTE)
  expect(apiEventDetail).toHaveBeenCalledTimes(3)
  // The start boundary at +20min triggers the next one.
  await vi.advanceTimersByTimeAsync(14 * MINUTE)
  expect(apiEventDetail).toHaveBeenCalledTimes(4)
})

test("a failed background refetch keeps the sidebar rendered", async () => {
  apiEventDetail.mockClear()
  let calls = 0
  apiEventDetail.mockImplementation(() => {
    calls++
    if (calls === 1) {
      return Promise.resolve({ data: makeEvent(20 * MINUTE), error: undefined })
    }
    return Promise.reject(new Error("network down"))
  })
  const result = render(() => (
    <QueryClientProvider client={new QueryClient({})}>
      <DetailSidebar eventid="test-session" />
    </QueryClientProvider>
  ))
  await vi.advanceTimersByTimeAsync(0)
  expect(result.container.textContent).toContain("Attend this session")

  // Cross the join-opens boundary: the refetch fails (plus retries), but the
  // sidebar must keep showing the stale data instead of the error boundary.
  await vi.advanceTimersByTimeAsync(6 * MINUTE)
  await vi.advanceTimersByTimeAsync(30_000)
  expect(calls).toBeGreaterThan(1)
  expect(result.container.textContent).toContain("Attend this session")
})
