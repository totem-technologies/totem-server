import { getCsrfToken } from "./csrf"

export async function postData(
  url: string,
  data: Record<string, unknown> = {}
): Promise<Response> {
  return await fetch(url, {
    method: "POST",
    body: new URLSearchParams({
      csrfmiddlewaretoken: getCsrfToken(),
      ...data,
    }),
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      Accept: "application/json",
    },
  })
}

/** The `{error}` message from a failed postData response, or the fallback. */
export async function postErrorMessage(
  response: Response,
  fallback: string
): Promise<string> {
  try {
    const { error } = (await response.json()) as { error?: string }
    return error || fallback
  } catch {
    return fallback
  }
}
