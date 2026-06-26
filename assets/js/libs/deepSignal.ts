import type { Signal } from "solid-js"
import { createStore, reconcile, unwrap } from "solid-js/store"

export function createDeepSignal<T>(value: T): Signal<T> {
  const [store, setStore] = createStore({
    value,
  })
  return [
    // eslint-disable-next-line solid/reactivity -- generic store accessor, not a component scope
    () => store.value,
    // eslint-disable-next-line solid/reactivity -- generic store setter, not a component scope
    (v: T) => {
      const unwrapped = unwrap<T>(store.value)
      // oxlint-disable-next-line no-unused-expressions -- short-circuit invokes the updater fn and reassigns v in place
      typeof v === "function" && (v = v(unwrapped))
      setStore("value", reconcile(v))
      return store.value
    },
  ] as Signal<T>
}
