export default function () {
  // Timezone settings. See TimezoneMiddleware in utils/middleware.py
  // If timezone isn't set, refresh page.
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone // e.g. "America/New_York"
  const hasZimzone = document.cookie
    .split(";")
    .some((item) => item.trim().startsWith("totem_timezone="))
  if (timezone && !hasZimzone) {
    document.cookie = `totem_timezone=${timezone}; SameSite=Strict`
    location.reload()
  }
}
