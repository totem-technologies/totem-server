import { render } from "@solidjs/testing-library"
import userEvent from "@testing-library/user-event"
import { beforeEach, expect, test, vi } from "vitest"
import type { SpaceDetailSchema } from "../client"
import { SpaceCard } from "./forYou"

const postData = vi.fn(() =>
  Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }))
)
vi.mock("@/libs/postData", () => ({
  postData: (...args: unknown[]) =>
    (postData as (...a: unknown[]) => Promise<Response>)(...args),
}))

const user = userEvent.setup()

beforeEach(() => {
  postData.mockClear()
})

function makeSpace(
  overrides: Partial<SpaceDetailSchema> = {}
): SpaceDetailSchema {
  return {
    slug: "test-space",
    title: "Test Space",
    image_link: null,
    short_description: "A space for testing",
    content: "<p>About this space</p>",
    author: {
      name: "Test Keeper",
      profile_avatar_type: "TD",
      date_created: "2023-01-01T00:00:00.000Z",
    },
    next_event: {
      slug: "test-session",
      start: "2030-01-01T18:00:00.000Z",
      link: "/spaces/session/test-session/",
      title: "Test Session",
      seats_left: 4,
      duration: 60,
      meeting_provider: "livekit",
      cal_link: "https://totem.org/spaces/session/test-session/",
      rsvp_url: "/spaces/rsvp/test-session/",
      attending: false,
      cancelled: false,
      open: true,
      joinable: false,
    },
    category: "Testing",
    subscribers: 5,
    recurring: "Once a week",
    price: 0,
    ...overrides,
  }
}

test("renders space info with attend button", () => {
  const result = render(() => <SpaceCard space={makeSpace()} />)
  expect(result.container.textContent).toContain("Test Space")
  expect(result.container.textContent).toContain("with Test Keeper")
  expect(result.getByRole("button", { name: /attend/i })).toBeTruthy()
})

test("attend click posts rsvp and flips to attending", async () => {
  const result = render(() => <SpaceCard space={makeSpace()} />)
  await user.click(result.getByRole("button", { name: /attend/i }))
  expect(postData).toHaveBeenCalledWith("/spaces/rsvp/test-session/")
  expect(result.container.textContent).toContain("Attending")
})

test("failed attend rolls back and shows an error", async () => {
  postData.mockResolvedValueOnce(
    new Response(JSON.stringify({ error: "This session is full." }), {
      status: 400,
    })
  )
  const result = render(() => <SpaceCard space={makeSpace()} />)
  await user.click(result.getByRole("button", { name: /attend/i }))
  expect(result.getByRole("button", { name: /attend/i })).toBeTruthy()
  expect(result.container.textContent).toContain("This session is full.")
})

test("already attending shows attending link instead of button", () => {
  const space = makeSpace()
  space.next_event!.attending = true
  const result = render(() => <SpaceCard space={space} />)
  expect(result.queryByRole("button", { name: /attend/i })).toBeNull()
  expect(result.container.textContent).toContain("Attending")
})
