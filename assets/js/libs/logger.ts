interface Logger {
  enableLogger: () => void
  disableLogger: () => void
}

const logger = (() => {
  let oldConsoleLog: typeof console.log | null = null
  const pub = {} as Logger

  pub.enableLogger = function enableLogger(): void {
    if (oldConsoleLog == null) return

    globalThis.console.log = oldConsoleLog
  }

  pub.disableLogger = function disableLogger(): void {
    oldConsoleLog = globalThis.console.log
    globalThis.console.log = () => {}
  }

  return pub
})()

function init(debug: boolean): void {
  if (debug === true) logger.enableLogger()
  else logger.disableLogger()
}

export default init
