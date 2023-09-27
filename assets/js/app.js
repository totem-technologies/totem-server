import components from "./components"
import emailSpellChecker from "./emailSpellCheck"
import timezoneDetect from "./timezone"

import logger from "./logger"

dismiss_alert = function (e) {
  e.closest(".alert-dismissible").remove()
}

components()
timezoneDetect()
window.addEventListener("DOMContentLoaded", () => {
  emailSpellChecker()
})

logger(window.TOTEM_DATA.debug)
