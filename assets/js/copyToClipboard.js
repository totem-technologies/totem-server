function copyTextToClipboard(element) {
  const text = element.getAttribute("data-copy")
  navigator.clipboard.writeText(text)
  element.innerHTML = "Copied!"
}

function init() {
  window.copyTextToClipboard = copyTextToClipboard
}

export default init
