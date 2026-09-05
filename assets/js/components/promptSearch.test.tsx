import { fireEvent, render, within } from "@solidjs/testing-library"
import { afterEach, beforeEach, expect, test } from "vitest"
import PromptSearch from "./promptSearch"

const prompts = [
  { prompt: "What brings you joy?", tags: ["gratitude"] },
  { prompt: "How do you rest?", tags: ["wellbeing"] },
  { prompt: "Who makes you laugh?", tags: ["gratitude"] },
]

beforeEach(() => {
  window.history.replaceState({}, "", "/")
  const data = document.createElement("script")
  data.id = "prompt-search-data"
  data.type = "application/json"
  data.textContent = JSON.stringify(prompts)
  document.body.append(data)
})

afterEach(() => {
  document.getElementById("prompt-search-data")?.remove()
  window.history.replaceState({}, "", "/")
})

test("updates results as the query changes and restores them when cleared", () => {
  const view = render(() => <PromptSearch dataid="prompt-search-data" />)
  const input = view.getByRole<HTMLInputElement>("searchbox")
  const results = within(view.getByRole("list"))
  expect(results.getAllByRole("listitem")).toHaveLength(3)

  fireEvent.input(input, { target: { value: "rest" } })
  expect(results.getAllByRole("listitem")).toHaveLength(1)
  expect(document.body.contains(results.getByText("How do you rest?"))).toBe(
    true
  )

  fireEvent.input(input, { target: { value: "joy" } })
  expect(results.getAllByRole("listitem")).toHaveLength(1)
  expect(
    document.body.contains(results.getByText("What brings you joy?"))
  ).toBe(true)

  fireEvent.input(input, { target: { value: "zzzzzzzz" } })
  expect(results.queryAllByRole("listitem")).toHaveLength(0)

  fireEvent.click(view.getByRole("button", { name: "X Clear search" }))
  expect(results.getAllByRole("listitem")).toHaveLength(3)
  expect(input.value).toBe("")
})

test("loads the URL query and updates results when a tag is selected", () => {
  window.history.replaceState({}, "", "/?search=rest")
  const view = render(() => <PromptSearch dataid="prompt-search-data" />)
  const results = within(view.getByRole("list"))
  expect(results.getAllByRole("listitem")).toHaveLength(1)
  expect(document.body.contains(results.getByText("How do you rest?"))).toBe(
    true
  )

  fireEvent.click(view.getByRole("button", { name: "gratitude" }))
  expect(results.getAllByRole("listitem")).toHaveLength(2)
  expect(
    document.body.contains(results.getByText("What brings you joy?"))
  ).toBe(true)
  expect(
    document.body.contains(results.getByText("Who makes you laugh?"))
  ).toBe(true)
  expect(view.getByRole<HTMLInputElement>("searchbox").value).toBe("gratitude")
  expect(window.location.search).toBe("?search=gratitude")
})
