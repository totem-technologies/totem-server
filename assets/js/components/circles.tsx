import {
  For,
  Match,
  Show,
  Switch,
  createEffect,
  createResource,
  createSignal,
} from "solid-js"
import { CircleEventSchema, CirclesService } from "../client/index"
import styles from "./circles.module.css"

type QueryParams = {
  limit: number
  category: string
}

const defaultParams: QueryParams = {
  limit: 20,
  category: "",
}

function getQueryParams(): QueryParams {
  var urlParams = new URLSearchParams(window.location.search)
  return {
    limit: parseInt(urlParams.get("limit") || defaultParams.limit.toString()),
    category: urlParams.get("category") || defaultParams.category,
  }
}

function timestampToDateString(timestamp: string) {
  return new Date(timestamp).toLocaleDateString()
}

function timestampToTimeString(timestamp: string) {
  // Convert timestamp to HH:MM AM/PM Timezone
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "numeric",
    timeZoneName: "short",
  })
}

function Circles() {
  const [params, setParams] = createSignal<QueryParams>(getQueryParams())
  createEffect(() => {
    const urlParams = new URLSearchParams(params() as any)
    window.history.replaceState(null, "", "?" + urlParams.toString())
    refetch()
  })
  const [events, { mutate, refetch }] = createResource(async () => {
    return CirclesService.totemCirclesApiListCircles(params())
  })
  return (
    <div class={`${styles.something}`}>
      <button onClick={refetch}>Refresh</button>
      <button onClick={() => setParams(defaultParams)}>Reset</button>
      <Show when={events()} fallback={<div>Loading...</div>}>
        <Switch fallback={<div>No Circles</div>}>
          <Match when={events()}>
            <ul>
              <For each={events()!.items}>
                {(event) => <Event event={event} />}
              </For>
            </ul>
          </Match>
          <Match when={events.error}>
            <div>Error: {events.error.message}</div>
          </Match>
        </Switch>
      </Show>
      <button
        onClick={() => setParams({ ...params(), limit: params().limit + 10 })}>
        More
      </button>
    </div>
  )
}

function Event(props: { event: CircleEventSchema }) {
  return (
    <a
      href={`/circles/${props.event.slug}`}
      class="flex items-center justify-center gap-5 rounded-2xl p-5 hover:bg-white">
      {/* <div>{% avatar event.circle.author size=50 %}</div>
    <div class="flex-grow">
      <p class="font-bold">{{ event.circle.title }}</p>
      <p class="text-sm">with {{ event.circle.author.name }}</p>
      <p class="text-sm">{{ event.start|date:"g:i a T" }}</p>
    </div>
    <div class="text-2xl">→</div> */}
    </a>
  )
}

Circles.tagName = "t-circles"
Circles.propsDefault = {}
export default Circles
