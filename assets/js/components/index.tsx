import { QueryClient, QueryClientProvider } from "@tanstack/solid-query"
import { customElement, noShadowDOM } from "solid-element"
import { Suspense } from "solid-js"
import Avatar from "./avatar"
import Circles from "./circles"
import DetailSidebar from "./detailSidebar"
import ErrorBoundary from "./errors"
import PromptSearch from "./promptSearch"
import Tooltip from "./tooltip"
var components = [PromptSearch, Circles, Avatar, Tooltip, DetailSidebar]

export default function () {
  components.forEach((c) => {
    customElementWC(c.tagName, c.propsDefault || {}, c)
  })
}

const queryClient = new QueryClient({})

function customElementWC(name: string, propDefaults: any, Component: any) {
  customElement(name, propDefaults, (props: any, { element }) => {
    noShadowDOM()
    const slots = element.querySelectorAll("[slot]")
    // Add type annotation for props
    slots.forEach((slot: any) => {
      // eslint-disable-next-line solid/no-innerhtml
      props[slot.attributes["slot"].value] = <div innerHTML={slot.innerHTML} />
      slot.remove()
    })
    const children = element.innerHTML
    element.innerHTML = ""
    return (
      <QueryClientProvider client={queryClient}>
        <ErrorBoundary>
          <Suspense fallback={"Loading..."}>
            <Component {...props}>{children}</Component>
          </Suspense>
        </ErrorBoundary>
      </QueryClientProvider>
    )
  })
}
