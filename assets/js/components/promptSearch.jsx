import { For, createEffect, createSignal, onMount } from "solid-js"

function Tag(props) {
  return (
    <button
      onClick={() => props.onClick(props.tag)}
      type="button"
      class="mr-2 mt-1 inline-flex items-center rounded-full bg-tyellow px-3 py-1 text-xs font-medium leading-4 text-gray-700 hover:opacity-70"
    >
      {props.tag}
    </button>
  )
}

function Prompt(props) {
  return (
    <li class="mb-2 rounded-lg border-2 bg-white px-4 py-2">
      <div class="pb-3">{props.prompt}</div>
      <For each={props.tags}>
        {(tag) => <Tag onClick={props.tagClick} tag={tag} />}
      </For>
    </li>
  )
}

function PromptSearch(props) {
  const [search, setSearch] = createSignal(
    new URLSearchParams(window.location.search).get("search") || ""
  )
  const [data, setData] = createSignal([])

  onMount(() => {
    let data = JSON.parse(document.getElementById(props.dataid).textContent)
    setData(data)
  })

  // eslint-disable-next-line no-undef
  const uf = new uFuzzy({ outOfOrder: false })
  const tags = () => {
    return [
      ...new Set(
        data()
          .map((r) => r.tags)
          .flat()
      ),
    ].sort()
  }
  const haystack = () => {
    return data().map((r) => `${r.prompt} ${r.tags.join(" ")}`)
  }
  const items = () => {
    if (search() === "") {
      return data()
    } else {
      // eslint-disable-next-line no-unused-vars
      let [idxs, _info, order] = uf.search(haystack(), search())
      if (order) {
        return order.map((i) => idxs.map((i) => data()[i])[i])
      }
    }
  }

  createEffect(() => {
    // add search to url
    const term = search()
    if (term) {
      window.history.pushState({}, "", `?search=${term}`)
    } else {
      window.history.pushState({}, "", window.location.pathname)
    }
  })

  return (
    <div>
      <div class="py-5">
        <div class="relative">
          <div class="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
            <svg
              aria-hidden="true"
              class="h-5 w-5 text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
          <input
            type="search"
            value={search()}
            onInput={(e) => setSearch(e.target.value)}
            class="block w-full rounded-lg border border-gray-300 bg-gray-50 p-4 pl-10 text-sm text-gray-900 focus:border-blue-500 focus:ring-blue-500 "
            placeholder="Search prompts..."
            required
          />
        </div>
        <div>
          <button
            onClick={() => setSearch("")}
            type="button"
            class="mt-2 rounded-full bg-gray-200 px-3 py-1 text-xs font-medium leading-4 text-gray-700 hover:opacity-70"
          >
            X Clear search
          </button>
        </div>
      </div>
      <For each={tags()}>{(tag) => <Tag onClick={setSearch} tag={tag} />}</For>
      <ul class="pt-10">
        <For each={items()}>
          {(item) => (
            <Prompt
              prompt={item.prompt}
              tagClick={setSearch}
              tags={item.tags}
            />
          )}
        </For>
      </ul>
    </div>
  )
}

PromptSearch.tagName = "t-promptsearch"
PromptSearch.propsDefault = {
  dataid: "prompt-search-data",
}
export default PromptSearch
