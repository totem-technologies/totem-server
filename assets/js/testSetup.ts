// Shared vitest environment shims (registered via setupFiles in vitest.config.ts).
import { vi } from "vitest"

// App-level globals normally provided by the Django base template.
globalThis.TOTEM_DATA = {
  debug: false,
  is_authenticated: true,
  reload_on_login: false,
}
globalThis.atcb_action = vi.fn(() => Promise.resolve(""))

// jsdom does not implement <dialog> methods.
HTMLDialogElement.prototype.showModal = function (this: HTMLDialogElement) {
  this.setAttribute("open", "")
}
HTMLDialogElement.prototype.close = function (this: HTMLDialogElement) {
  this.removeAttribute("open")
}
