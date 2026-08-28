// Delegated handlers for declarative click actions in server-rendered
// templates. Inline onclick= handlers are blocked by our CSP (nonces only
// cover <script> bodies, not attributes), so templates use data attributes:
//
//   <a data-copy="some text">Copy link</a>
//   <button data-show-modal="share_modal">Share</button>
//   <button data-dismiss-alert>x</button>

function init(): void {
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement | null
    if (!target) return

    const copyEl = target.closest<HTMLElement>("[data-copy]")
    if (copyEl) {
      navigator.clipboard.writeText(copyEl.getAttribute("data-copy") ?? "")
      copyEl.innerHTML = "Copied!"
      return
    }

    const modalEl = target.closest<HTMLElement>("[data-show-modal]")
    if (modalEl) {
      const dialog = document.getElementById(modalEl.getAttribute("data-show-modal") ?? "")
      if (dialog instanceof HTMLDialogElement) {
        dialog.showModal()
      }
      return
    }

    target.closest<HTMLElement>("[data-dismiss-alert]")?.closest(".alert-dismissible")?.remove()
  })
}

export default init
