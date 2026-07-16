import { render } from "@solidjs/testing-library"
import { createRoot } from "solid-js"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import SessionCountdown, {
  createSessionClock,
  type SessionTiming,
} from "./sessionCountdown"
import { MINUTE, sessionTimes } from "./testHelpers"

const NOW = new Date("2030-01-01T12:00:00.000Z")

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

function makeTiming(
  startOffsetMs: number,
  overrides: Partial<SessionTiming> = {}
): SessionTiming {
  return {
    ...sessionTimes(NOW.getTime() + startOffsetMs),
    joinable: false,
    ended: false,
    ...overrides,
  }
}

function canJoinAt(
  startOffsetMs: number,
  overrides: Partial<SessionTiming> = {}
): boolean {
  let result = false
  createRoot((dispose) => {
    result = createSessionClock(() =>
      makeTiming(startOffsetMs, overrides)
    ).canJoin()
    dispose()
  })
  return result
}

// --- canJoin: when is the button revealed? ---

test("closed outside the join window, open inside it", () => {
  expect(canJoinAt(2 * 24 * 60 * MINUTE)).toBe(false)
  expect(canJoinAt(16 * MINUTE)).toBe(false)
  expect(canJoinAt(10 * MINUTE)).toBe(true)
  expect(canJoinAt(-5 * MINUTE)).toBe(true)
})

test("join opens live as the clock crosses the window", () => {
  createRoot((dispose) => {
    const clock = createSessionClock(() => makeTiming(16 * MINUTE))
    expect(clock.canJoin()).toBe(false)
    vi.advanceTimersByTime(2 * MINUTE)
    expect(clock.canJoin()).toBe(true)
    dispose()
  })
})

test("beyond grace, only the server's joinable reopens it", () => {
  expect(canJoinAt(-30 * MINUTE)).toBe(false)
  expect(canJoinAt(-30 * MINUTE, { joinable: true })).toBe(true)
})

test("open-ended session (null close) stays joinable through overruns", () => {
  // LiveKit rejoin: the server is the only end signal, so the scheduled
  // end must not hide the button.
  expect(canJoinAt(-30 * MINUTE, { join_closes_at: null })).toBe(true)
  expect(
    canJoinAt(-70 * MINUTE, { join_closes_at: null, joinable: true })
  ).toBe(true)
})

test("open-ended session closes once the server says ended", () => {
  expect(canJoinAt(-70 * MINUTE, { join_closes_at: null, ended: true })).toBe(
    false
  )
  expect(
    canJoinAt(-70 * MINUTE, {
      join_closes_at: null,
      joinable: false,
      ended: true,
    })
  ).toBe(false)
})

test("ended session is closed even if joinable is stale-true", () => {
  expect(canJoinAt(-2 * 60 * MINUTE, { joinable: true })).toBe(false)
})

// --- SessionCountdown: the status line ---

function renderCountdown(
  startOffsetMs: number,
  overrides: Partial<SessionTiming> = {}
) {
  return render(() => (
    <SessionCountdown session={makeTiming(startOffsetMs, overrides)} />
  ))
}

test("far future session shows relative time", () => {
  const result = renderCountdown(2 * 24 * 60 * MINUTE)
  expect(result.container.textContent).toContain("in 2 days")
})

test("started session shows happening now", () => {
  const result = renderCountdown(-5 * MINUTE)
  expect(result.container.textContent?.toLowerCase()).toContain("happening now")
})

test("overrunning open-ended session is not called ended", () => {
  const result = renderCountdown(-70 * MINUTE, {
    join_closes_at: null,
    joinable: true,
  })
  expect(result.container.textContent?.toLowerCase()).not.toContain("ended")
})

test("ended session shows ended", () => {
  const result = renderCountdown(-2 * 60 * MINUTE)
  expect(result.container.textContent?.toLowerCase()).toContain("ended")
})
