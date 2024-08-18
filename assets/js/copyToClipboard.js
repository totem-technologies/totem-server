function copyTextToClipboard(element) {
  const text = element.getAttribute("data-copy")
  globalThis.navigator.clipboard.writeText(text)
  element.innerHTML = "Copied!"
}

function init() {
  globalThis.copyTextToClipboard = copyTextToClipboard
}

export default init
