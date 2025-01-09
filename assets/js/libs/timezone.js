function setTimeZoneCookie() {
  // Timezone settings. See TimezoneMiddleware in utils/middleware.py
  // If timezone isn't set in cookies, set it. Pages can force a reload if they need to.
  const timezone = getTimeZone() // e.g. "America/New_York"
  const hasTimezone = globalThis.document.cookie
    .split(";")
    .some((item) => item.trim().startsWith("totem_timezone="))
  if (timezone && !hasTimezone) {
    globalThis.document.cookie = `totem_timezone=${timezone}; SameSite=Strict; Secure; path=/; max-age=31536000`
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
