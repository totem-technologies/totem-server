var logger = (function () {
  var oldConsoleLog = null
  var pub = {}

  pub.enableLogger = function enableLogger() {
    if (oldConsoleLog == null) return

    globalThis["console"]["log"] = oldConsoleLog
  }

  pub.disableLogger = function disableLogger() {
    oldConsoleLog = globalThis.console.log
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    globalThis["console"]["log"] = function () {}
  }

  return pub
})()

function init(debug) {
  if (debug === true) logger.enableLogger()
  else logger.disableLogger()
}

export default init
