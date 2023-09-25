import Alpine from "alpinejs"
import dropdown from "./dropdown"
import emailSpellChecker from "./emailSpellCheck"
import search from "./promptsearch"

import logger from "./logger"

dismiss_alert = function (e) {
  e.closest(".alert-dismissible").remove()
}

// Timezone settings. See TimezoneMiddleware in utils/middleware.py
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone // e.g. "America/New_York"
document.cookie = `totem_timezone=${timezone}; SameSite=Strict`

Alpine.data("dropdown", dropdown)
Alpine.data("search", search)
Alpine.start()
window.addEventListener("DOMContentLoaded", () => {
  emailSpellChecker()
})

logger(window.TOTEM_DATA.debug)
