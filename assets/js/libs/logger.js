const logger = (() => {
  let oldConsoleLog = null
  const pub = {}

  pub.enableLogger = function enableLogger() {
    if (oldConsoleLog == null) return

    globalThis.console.log = oldConsoleLog
  }

  pub.disableLogger = function disableLogger() {
    oldConsoleLog = globalThis.console.log
    globalThis.console.log = () => {}
  }

  return pub
})()

function init(debug) {
  if (debug === true) logger.enableLogger()
  else logger.disableLogger()
}

export default init
