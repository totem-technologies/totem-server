function copyTextToClipboard(element: HTMLElement): void {
  const text = element.getAttribute("data-copy") ?? ""
  globalThis.navigator.clipboard.writeText(text)
  element.innerHTML = "Copied!"
}

declare global {
  interface Window {
    copyTextToClipboard: (element: HTMLElement) => void
  }
}

function init(): void {
  globalThis.copyTextToClipboard = copyTextToClipboard
}

export default init
