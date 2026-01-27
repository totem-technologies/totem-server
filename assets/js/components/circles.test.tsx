import { render } from "@solidjs/testing-library"
import userEvent from "@testing-library/user-event"
import { expect, test } from "vitest"
import { MobileEvent } from "./circles"

const _ = userEvent.setup()

test("increments value", async () => {
  const result = render(() => (
    <MobileEvent
      event={{
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
        start: "2023-01-01T00:00:00.000Z",
        slug: "test-event",
        date_created: "2023-01-01T00:00:00.000Z",
        date_modified: "2023-01-01T00:00:00.000Z",
        title: "Test Event",
      }}
    />
  ))
  const html = result.container.innerHTML
  expect(html).toContain("Test Space")
  expect(html).toContain("Test Event")
  expect(html).not.toContain("Invalid")
})
