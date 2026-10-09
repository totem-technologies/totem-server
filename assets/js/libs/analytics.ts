declare global {
  // Defined by the GA4 snippet in _analytics.html, which only loads in production.
  var gtag: ((...args: unknown[]) => void) | undefined
}

/**
 * Report a confirmed session registration to GA4, so registrations can be
 * attributed to traffic sources. Call only after the server confirms the
 * spot was saved. Sends public slugs only, never personal data.
 */
export function trackSessionRegistration(
  sessionSlug: string,
  spaceSlug: string
): void {
  globalThis.gtag?.("event", "session_registration_complete", {
    totem_session_id: sessionSlug,
    space_id: spaceSlug,
  })
}
