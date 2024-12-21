import { QueryClient, QueryClientProvider } from "@tanstack/solid-query"
import { customElement, noShadowDOM } from "solid-element"
import type { Component, JSXElement } from "solid-js"
import Avatar from "./avatar"
import Circles from "./circles"
import DetailSidebar from "./detailSidebar"
import { EditAvatar } from "./editAvatar"
import ErrorBoundary from "./errors"
import EventCalendar from "./eventCalendar"
import PromptSearch from "./promptSearch"
import Time from "./time"
import Tooltip from "./tooltip"

type WCComponent = Component & {
  tagName: string
  propsDefault: Record<string, string | number | null | JSXElement>
}

const components: WCComponent[] = [
  PromptSearch,
  Circles,
  Avatar,
  Tooltip,
  DetailSidebar,
  EventCalendar,
  Time,
  EditAvatar,
]

type CustomElementProps = (typeof components)[number]["propsDefault"] & {
  children?: JSXElement
}

export default function () {
  for (const c of components) {
    customElementWC(c.tagName, c.propsDefault || {}, c)
  }
}

const queryClient = new QueryClient({})

function customElementWC(
  name: string,
  propDefaults: CustomElementProps,
  Components: Component<CustomElementProps>
) {
  customElement(
    name,
    propDefaults,
    (props: CustomElementProps, { element }) => {
      noShadowDOM()
      // eslint-disable-next-line @typescript-eslint/no-unsafe-call
      const slots = element.querySelectorAll(
        "[slot]"
      ) as NodeListOf<HTMLSlotElement>
      for (const slot of slots) {
        const slotName = slot.getAttribute("slot")
        if (slotName !== null) {
          // eslint-disable-next-line solid/no-innerhtml
          props[slotName] = <div innerHTML={slot.innerHTML} />
          slot.remove()
        }
      }

      props.children = element.innerHTML as string | undefined
      element.innerHTML = ""
      return (
        <QueryClientProvider client={queryClient}>
          <ErrorBoundary>
            <Components {...props} />
          </ErrorBoundary>
        </QueryClientProvider>
      )
    }
  )
}
