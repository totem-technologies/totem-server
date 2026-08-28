// Delegated copy-to-clipboard for admin pages. Inline onclick handlers are
// blocked by the site CSP (nonces don't cover handler attributes), so admin
// columns render a [data-copy] attribute and this listener does the work.
document.addEventListener("click", function (event) {
  const el = event.target.closest("[data-copy]")
  if (!el) return
  event.preventDefault()
  navigator.clipboard.writeText(el.getAttribute("data-copy") || "")
  const original = el.innerHTML
  el.innerHTML = "Copied!"
  setTimeout(function () {
    el.innerHTML = original
  }, 1500)
})
