import htmx from "htmx.org"

function init() {
  htmx.config.refreshOnHistoryMiss = true
  htmx.config.historyCacheSize = 0
  window.htmx = htmx
}

export default init
