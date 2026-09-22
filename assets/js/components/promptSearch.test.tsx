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

  expect(view.getByText("No prompts found")).toBeDefined()
  expect(view.getByRole("status").textContent).toContain("0 prompts")

  fireEvent.click(view.getByRole("button", { name: "Clear search" }))
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
  expect(
    within(view.getByRole("region", { name: "Find prompts" }))
      .getByRole("button", { name: "gratitude" })
      .getAttribute("aria-pressed")
  ).toBe("true")

  fireEvent.click(view.getByRole("button", { name: "All prompts" }))
  expect(results.getAllByRole("listitem")).toHaveLength(3)
  expect(window.location.search).toBe("")
})

test("encodes shared searches while preserving other URL parameters and the hash", () => {
  window.history.replaceState({}, "", "/?source=guide#library")
  const view = render(() => <PromptSearch dataid="prompt-search-data" />)
  const input = view.getByRole("searchbox", {
    name: "Search the prompt library",
  })
  fireEvent.input(input, { target: { value: "rest & joy #1" } })

  const url = new URL(window.location.href)
  expect(url.searchParams.get("search")).toBe("rest & joy #1")
  expect(url.searchParams.get("source")).toBe("guide")
  expect(url.hash).toBe("#library")

  fireEvent.click(view.getByRole("button", { name: "Clear search" }))
  expect(window.location.search).toBe("?source=guide")
  expect(window.location.hash).toBe("#library")
})

test("explains when the library has no prompts", () => {
  document.getElementById("prompt-search-data")!.textContent = "[]"
  const view = render(() => <PromptSearch dataid="prompt-search-data" />)
  expect(view.getByText("More conversations to come")).toBeDefined()
  expect(view.queryByText("No prompts found")).toBeNull()
  expect(view.getByRole("status").textContent).toContain("0 prompts")
})
