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
