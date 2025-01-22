import Cookies from "js-cookie"

function setTimeZoneCookie() {
  // Timezone settings. See TimezoneMiddleware in utils/middleware.py
  // If timezone isn't set in cookies, or if the timezone is not current, set it. Pages can force a reload if they need to.
  const timezone = getTimeZone() // e.g. "America/New_York"
  const timezoneKey = "totem_timezone"
  const currentTimezone = Cookies.get(timezoneKey)
  if (currentTimezone !== timezone) {
    Cookies.set(timezoneKey, timezone, {
      expires: 365,
      secure: true,
      sameSite: "Strict",
    }) // 1 year
  }
}

function getTimeZone() {
  try {
    if (Intl?.DateTimeFormat) {
      const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
      return timeZone || "UTC" // fallback to UTC if timeZone is undefined
    }
    return "UTC" // fallback if Intl.DateTimeFormat isn't available
  } catch (error) {
    console.error("Error getting timezone:", error)
    return "UTC" // fallback in case of any errors
  }
}

export { setTimeZoneCookie, getTimeZone }
