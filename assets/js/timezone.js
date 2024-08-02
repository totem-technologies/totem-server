export default function () {
  // Timezone settings. See TimezoneMiddleware in utils/middleware.py
  // If timezone isn't set in cookies, set it. Pages can force a reload if they need to.
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone // e.g. "America/New_York"
  const hasTimezone = document.cookie
    .split(";")
    .some((item) => item.trim().startsWith("totem_timezone="))
  if (timezone && !hasTimezone) {
    document.cookie = `totem_timezone=${timezone}; SameSite=Strict; Secure; path=/; max-age=31536000`
  }
}
