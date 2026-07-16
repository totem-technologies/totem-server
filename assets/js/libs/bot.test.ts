import { beforeEach, describe, expect, it, vi } from "vitest"
import initBot from "./bot"

function makeForm() {
  document.body.innerHTML = `
    <form data-bot="true" method="post">
      <input type="email" name="email" />
      <button type="submit">Continue</button>
    </form>`
  const form = document.querySelector("form") as HTMLFormElement
  // jsdom doesn't implement real form submission
  form.submit = vi.fn()
  return form
}

function submit(form: HTMLFormElement) {
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }))
}

describe("bot form handling", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=test-token"
  })

  it("injects the CSRF token and submits", () => {
    const form = makeForm()
    initBot()
    submit(form)
    const input = form.querySelector(
      'input[name="csrfmiddlewaretoken"]'
    ) as HTMLInputElement
    expect(input?.value).toBe("test-token")
    expect(form.submit).toHaveBeenCalledOnce()
  })

  it("disables the submit button so double clicks cannot submit twice", () => {
    const form = makeForm()
    initBot()
    const button = form.querySelector("button") as HTMLButtonElement
    submit(form)
    expect(button.disabled).toBe(true)
  })

  it("ignores repeat submit events while a submission is in flight", () => {
    const form = makeForm()
    initBot()
    submit(form)
    submit(form)
    expect(form.submit).toHaveBeenCalledTimes(1)
    expect(
      form.querySelectorAll('input[name="csrfmiddlewaretoken"]')
    ).toHaveLength(1)
  })

  it("also disables <input type=submit> controls", () => {
    document.body.innerHTML = `
      <form data-bot="true" method="post">
        <input class="btn" type="submit" value="Submit" />
      </form>`
    const form = document.querySelector("form") as HTMLFormElement
    form.submit = vi.fn()
    initBot()
    const control = form.querySelector("input[type=submit]") as HTMLInputElement
    submit(form)
    expect(control.disabled).toBe(true)
  })

  it("re-arms the form when the page is restored from bfcache", () => {
    const form = makeForm()
    initBot()
    const button = form.querySelector("button") as HTMLButtonElement
    submit(form)
    expect(button.disabled).toBe(true)

    // Simulate the browser restoring the page via back/forward cache.
    const pageshow = new Event("pageshow")
    Object.defineProperty(pageshow, "persisted", { value: true })
    window.dispatchEvent(pageshow)

    expect(button.disabled).toBe(false)
    submit(form)
    expect(form.submit).toHaveBeenCalledTimes(2)
    // The restored form must not accumulate duplicate token inputs.
    expect(
      form.querySelectorAll('input[name="csrfmiddlewaretoken"]')
    ).toHaveLength(1)
  })

  it("does not inject an empty token that would shadow a template token", () => {
    document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT"
    const form = makeForm()
    initBot()
    submit(form)
    expect(
      form.querySelector('input[name="csrfmiddlewaretoken"]')
    ).toBeNull()
    expect(form.submit).toHaveBeenCalledOnce()
  })
})
