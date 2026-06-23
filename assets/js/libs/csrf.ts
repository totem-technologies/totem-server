import Cookies from "js-cookie"

// Django stores the CSRF token in a non-HttpOnly cookie (CSRF_COOKIE_HTTPONLY is
// False in settings) so the frontend can read it and echo it back on unsafe
// requests, either as a hidden form field or the X-CSRFToken header.
export function getCsrfToken(): string {
  return Cookies.get("csrftoken") ?? ""
}
