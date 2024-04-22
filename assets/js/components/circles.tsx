import { For, Match, Suspense, Switch, createResource } from "solid-js"
import { CirclesService } from "../client/index"
import styles from "./circles.module.css"

function Circles() {
  const [circles, { mutate, refetch }] = createResource(
    CirclesService.totemCirclesApiListCircles
  )
  return (
    <div class={`${styles.something}`}>
      <h1>Circles</h1>
      <button onClick={refetch}>Refresh</button>
      <Suspense fallback={<div>Loading...</div>}>
        <Switch fallback={<div>No user</div>}>
          <Match when={circles()}>
            <ul>
              <For each={circles()}>
                {(circle) => <li>{circle.circle.title}</li>}
              </For>
            </ul>
          </Match>
          <Match when={circles.error}>
            <div>Error: {circles.error.message}</div>
          </Match>
        </Switch>
      </Suspense>
    </div>
  )
}

Circles.tagName = "t-circles"
Circles.propsDefault = {}
export default Circles
