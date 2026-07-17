import { beforeEach, describe, expect, it, vi } from "vitest"
import init from "./clickActions"

init()

function click(el: Element) {
  el.dispatchEvent(new MouseEvent("click", { bubbles: true }))
}

describe("data-copy", () => {
  beforeEach(() => {
    document.body.innerHTML = ""
    Object.assign(navigator, { clipboard: { writeText: vi.fn() } })
  })

  it("copies the attribute value and confirms", () => {
    document.body.innerHTML = `<a data-copy="https://totem.org/x">Copy link</a>`
    const el = document.querySelector("a") as HTMLAnchorElement
    click(el)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("https://totem.org/x")
    expect(el.innerHTML).toBe("Copied!")
  })

  it("works when the click lands on a child element", () => {
    document.body.innerHTML = `<a data-copy="text"><svg id="icon"></svg>Copy</a>`
    click(document.getElementById("icon") as Element)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("text")
  })
})

describe("data-dismiss-alert", () => {
  it("removes the enclosing dismissible alert", () => {
    document.body.innerHTML = `
      <div class="alert-dismissible"><button data-dismiss-alert>x</button></div>`
    click(document.querySelector("button") as Element)
    expect(document.querySelector(".alert-dismissible")).toBeNull()
  })
})

describe("data-show-modal", () => {
  beforeEach(() => {
    document.body.innerHTML = ""
  })

  it("opens the referenced dialog", () => {
    document.body.innerHTML = `
      <button data-show-modal="share_modal">Share</button>
      <dialog id="share_modal"></dialog>`
    const dialog = document.querySelector("dialog") as HTMLDialogElement
    // jsdom doesn't implement showModal
    dialog.showModal = vi.fn()
    click(document.querySelector("button") as Element)
    expect(dialog.showModal).toHaveBeenCalled()
  })

  it("ignores clicks with no matching dialog", () => {
    document.body.innerHTML = `<button data-show-modal="missing">Share</button>`
    expect(() => click(document.querySelector("button") as Element)).not.toThrow()
  })
})
