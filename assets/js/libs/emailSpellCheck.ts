import emailSpellChecker from "@zootools/email-spell-checker"

function debounce<T extends (e: Event) => void>(
  func: T,
  timeout = 300
): (...args: Parameters<T>) => void {
  let timer: ReturnType<typeof setTimeout>
  return (...args: Parameters<T>) => {
    globalThis.clearTimeout(timer)
    timer = globalThis.setTimeout(() => {
      func.apply(undefined, args)
    }, timeout)
  }
}

function init(): void {
  const emailInputs =
    globalThis.document.querySelectorAll<HTMLInputElement>("input[type=email]")
  for (const input of emailInputs) {
    function clearAlert(e: Event): void {
      const target = e.target as HTMLInputElement
      const alert = target.parentElement?.querySelector<HTMLElement>(
        ".email-alert-dismissible"
      )
      if (alert) {
        alert.remove()
      }
    }
    const myScript = (e: Event): void => {
      const target = e.target as HTMLInputElement
      const email = target.value.trim()
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
  }
}

export default init
