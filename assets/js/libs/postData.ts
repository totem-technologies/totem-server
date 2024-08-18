export async function postData(
  url: string,
  data: Record<string, unknown> = {}
): Promise<Response> {
  return await fetch(url, {
    method: "POST",
    body: new URLSearchParams({
      csrfmiddlewaretoken: window.TOTEM_DATA.csrf_token,
      ...data,
    }),
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      Accept: "application/json",
    },
  })
}
