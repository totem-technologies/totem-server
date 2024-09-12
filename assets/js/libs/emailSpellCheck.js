import emailSpellChecker from "@zootools/email-spell-checker"

function debounce(func, timeout = 300) {
  let timer
  return (...args) => {
    globalThis.clearTimeout(timer)
    timer = globalThis.setTimeout(() => {
      func.apply(this, args)
    }, timeout)
  }
}

function init() {
  globalThis.document.querySelectorAll("input[type=email]").forEach((input) => {
    function clearAlert(e) {
      const alert = e.target.parentElement.querySelector(
        ".email-alert-dismissible"
      )
      if (alert) {
        alert.remove()
      }
    }
    const myScript = (e) => {
      const email = e.target.value.trim()
      const suggestedEmail = emailSpellChecker.run({
        email,
      })
      clearAlert(e)
      if (!suggestedEmail) {
        return
      }
      const message = `<button class="text-sm">Is your email <strong>${suggestedEmail.full}</strong>?</button>`
      const alert = globalThis.document.createElement("div")
      alert.classList.add("email-alert-dismissible")
      alert.innerHTML = message
      alert.onclick = () => {
        clearAlert(e)
        input.value = suggestedEmail.full
      }
      input.after(alert)
    }
    input.addEventListener("keyup", debounce(myScript))
  })
}

export default init
