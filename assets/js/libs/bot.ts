import { getCsrfToken } from "./csrf"

/**
 * Initializes the bot detection functionality and attaches event listeners to forms with `data-bot="true"`.
 */

function submitControls(form: HTMLFormElement) {
  const controls: (HTMLButtonElement | HTMLInputElement)[] = []
  for (const el of form.querySelectorAll(
    "button[type=submit], input[type=submit]"
  )) {
    if (el instanceof HTMLButtonElement || el instanceof HTMLInputElement) {
      controls.push(el)
    }
  }
  return controls
}

export default function () {
  const forms = document.querySelectorAll('[data-bot="true"]')
  if (!forms) {
    return
  }
  for (const form of forms) {
    form.addEventListener("submit", (event) => {
      event.preventDefault()
      if (!(form instanceof HTMLFormElement) || form.dataset.submitting) {
        return
      }
      form.dataset.submitting = "true"
      const token = getCsrfToken()
      // Never inject an empty token: it would be the last POST value and
      // shadow a valid template-rendered {% csrf_token %} input.
      if (token) {
        const csrfInput = document.createElement("input")
        csrfInput.type = "hidden"
        csrfInput.name = "csrfmiddlewaretoken"
        csrfInput.value = token
        csrfInput.dataset.botInjected = "true"
        form.appendChild(csrfInput)
      }
      // Sending the PIN email is slow, so keep double clicks and repeat Enter
      // presses from submitting the form twice. Disabling before submit()
      // drops the control's own name/value from the POST, so data-bot forms
      // must not rely on which submit button was clicked (none do today).
      for (const control of submitControls(form)) {
        control.disabled = true
      }
      form.submit()
    })
  }
  // Back/forward-cache restores keep DOM and dataset state, which would leave
  // the form permanently locked. Re-arm it so "Back to resend" works.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) {
      return
    }
    for (const form of forms) {
      if (!(form instanceof HTMLFormElement)) {
        continue
      }
      delete form.dataset.submitting
      for (const control of submitControls(form)) {
        control.disabled = false
      }
      // Drop only the token input we injected; a template-rendered
      // {% csrf_token %} input must stay.
      for (const injected of form.querySelectorAll(
        "input[data-bot-injected]"
      )) {
        injected.remove()
      }
    }
  })
}
