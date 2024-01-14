import { load } from "@fingerprintjs/botd"

const botdPromise = load()

export default function () {
  const forms = document.querySelectorAll('[data-bot="true"]')
  forms.forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault()
      const botd = await botdPromise
      const result = await botd.detect()
      if (result.bot) {
        throw new Error("Bot detected")
      }
      var csrfInput = document.createElement("input")
      csrfInput.type = "hidden"
      csrfInput.name = "csrfmiddlewaretoken"
      csrfInput.value = window.TOTEM_DATA.csrf_token
      form.appendChild(csrfInput)
      form.submit()
    })
  })
}
