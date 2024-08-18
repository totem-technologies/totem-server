/**
 * Initializes the bot detection functionality and attaches event listeners to forms with `data-bot="true"`.
 */

export default function () {
  const forms = document.querySelectorAll('[data-bot="true"]')
  if (!forms) {
    return
  }
  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault()
      const csrfInput = document.createElement("input")
      csrfInput.type = "hidden"
      csrfInput.name = "csrfmiddlewaretoken"
      csrfInput.value = window.TOTEM_DATA.csrf_token
      form.appendChild(csrfInput)
      if (form instanceof HTMLFormElement) {
        form.submit()
      }
    })
  })
}
