import htmx from "htmx.org"

function init() {
  htmx.config.refreshOnHistoryMiss = true
  htmx.config.historyCacheSize = 0
  globalThis.htmx = htmx
}

export default init
