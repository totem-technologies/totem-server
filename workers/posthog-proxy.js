// Copy to https://dash.cloudflare.com/b5c38d4693831386902960215d12dac8/workers/services/edit/posthog-proxy/production
const API_HOST = "app.posthog.com" // Change to "eu.posthog.com" for the EU region

async function handleRequest(event) {
  const url = new URL(event.request.url)
  const pathname = url.pathname
  const search = url.search

  const pathWithParams = pathname + search
  if (pathname.startsWith("/static/")) {
    return retrieveStatic(event, pathWithParams)
  } else {
    return forwardRequest(event, pathWithParams)
  }
}

async function retrieveStatic(event, pathname) {
  let response = await caches.default.match(event.request)
  if (!response) {
    response = await fetch(`https://${API_HOST}${pathname}`)
    event.waitUntil(caches.default.put(event.request, response.clone()))
  }
  return response
}

async function forwardRequest(event, pathWithSearch) {
  const request = new Request(event.request)
  request.headers.delete("cookie")
  return await fetch(`https://${API_HOST}${pathWithSearch}`, request)
}

addEventListener("fetch", (event) => {
  event.passThroughOnException()
  event.respondWith(handleRequest(event))
})
