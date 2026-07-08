import { render } from "@solidjs/testing-library"
import { afterEach, beforeEach, expect, test, vi } from "vitest"
import SessionCountdown from "./sessionCountdown"

const NOW = new Date("2030-01-01T12:00:00.000Z")
const MINUTE = 60_000

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

function renderCountdown(startOffsetMs: number, joinable = "false") {
  const start = new Date(NOW.getTime() + startOffsetMs).toISOString()
  return render(() => (
    <SessionCountdown
      start={start}
      duration={60}
      joinurl="/spaces/join/test-session/"
      joinable={joinable}
    />
  ))
}

function joinButton(result: ReturnType<typeof renderCountdown>) {
  return result.queryByRole("link", { name: /join now/i })
}

test("far future session shows relative time, no join button", () => {
  const result = renderCountdown(2 * 24 * 60 * MINUTE)
  expect(result.container.textContent).toContain("in 2 days")
  expect(joinButton(result)).toBeNull()
})

test("session within the join window shows the join button", () => {
  const result = renderCountdown(10 * MINUTE)
  const btn = joinButton(result)
  expect(btn).toBeTruthy()
  expect(btn!.getAttribute("href")).toBe("/spaces/join/test-session/")
})

test("join button appears as the window opens", () => {
  const result = renderCountdown(16 * MINUTE)
  expect(joinButton(result)).toBeNull()
  vi.advanceTimersByTime(2 * MINUTE)
  expect(joinButton(result)).toBeTruthy()
})

test("started session shows happening now and join", () => {
  const result = renderCountdown(-5 * MINUTE)
  expect(result.container.textContent?.toLowerCase()).toContain("happening now")
  expect(joinButton(result)).toBeTruthy()
})

test("started beyond grace hides join unless server says joinable", () => {
  const noJoin = renderCountdown(-30 * MINUTE)
  expect(joinButton(noJoin)).toBeNull()
  const rejoin = renderCountdown(-30 * MINUTE, "true")
  expect(joinButton(rejoin)).toBeTruthy()
})

test("ended session shows ended, no join even if joinable", () => {
  const result = renderCountdown(-2 * 60 * MINUTE, "true")
  expect(result.container.textContent?.toLowerCase()).toContain("ended")
  expect(joinButton(result)).toBeNull()
})
