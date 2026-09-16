import uFuzzy from "@leeoniya/ufuzzy"
import {
  createEffect,
  createMemo,
  createSignal,
  For,
  type JSXElement,
  onMount,
  Show,
} from "solid-js"

interface TagProps {
  onClick: (tag: string) => void
  tag: string
  selected?: boolean
}

interface PromptItem {
  prompt: string
  tags: string[]
}

function Tag(props: TagProps) {
  return (
    <button
      onClick={() => props.onClick(props.tag)}
      type="button"
      aria-pressed={props.selected ?? false}
      class="focus-visible:outline-tpink-tint rounded-full border px-3.5 py-2 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2"
      classList={{
        "border-tmauve bg-tmauve text-white": props.selected,
        "border-tmauve/15 bg-tcreme/60 text-tdeepgray hover:border-tmauve/50 hover:bg-tmauve/10":
          !props.selected,
      }}>
      {props.tag}
    </button>
  )
}

function Prompt(props: {
  prompt: string
  tags: string[]
  search: string
  tagClick: (tag: string) => void
}) {
  return (
    <li class="border-tmauve/15 flex min-w-0 flex-col rounded-3xl border bg-white p-4 shadow-sm transition-shadow hover:shadow-md md:p-5">
      <span
        class="text-tmauve/60 mb-1 h-7 font-serif text-5xl leading-none"
        aria-hidden="true">
        “
      </span>
      <p class="text-tslate grow text-lg leading-relaxed font-medium text-pretty [overflow-wrap:anywhere]">
        {props.prompt}
      </p>
      <Show when={props.tags.length > 0}>
        <div class="mt-4 flex flex-wrap gap-2">
          <For each={props.tags}>
            {(tag) => (
              <Tag
                onClick={props.tagClick}
                tag={tag}
                selected={props.search === tag}
              />
            )}
          </For>
        </div>
      </Show>
    </li>
  )
}

function PromptSearch(props: { dataid?: string; children?: JSXElement }) {
  const [search, setSearch] = createSignal(
    new URLSearchParams(window.location.search).get("search") ?? ""
  )
  const [data, setData] = createSignal<PromptItem[]>([])

  onMount(() => {
    const data = JSON.parse(
      document.getElementById(props.dataid ?? "")?.textContent ?? "[]"
    ) as PromptItem[]
    setData(data)
  })

  const uf = new uFuzzy()
  const tags = createMemo(() =>
    [...new Set(data().flatMap((r) => r.tags))].sort()
  )
  const haystack = createMemo(() =>
    data().map((r) => `${r.prompt} ${r.tags.join(" ")}`)
  )
  const items = createMemo(() => {
    if (search() === "") {
      return data()
    }
    const [idxs, _info, order] = uf.search(haystack(), search(), 0)
    if (!order) return []
    const matches: PromptItem[] = []
    for (const i of order) {
      matches.push(data()[idxs[i]])
    }
    return matches
  })

  createEffect(() => {
    const url = new URL(window.location.href)
    const term = search()
    if (term) {
      url.searchParams.set("search", term)
    } else {
      url.searchParams.delete("search")
    }
    window.history.replaceState({}, "", url)
  })

  return (
    <div>
      <section
        aria-label="Find prompts"
        class="border-tmauve/15 rounded-3xl border bg-white p-4 shadow-sm md:p-5">
        <label for="prompt-search" class="mb-2 block">
          Search the prompt library
        </label>
        <div class="relative">
          <div class="text-tmauve pointer-events-none absolute inset-y-0 left-0 flex items-center pl-4">
            <svg
              aria-hidden="true"
              class="size-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </div>
          <input
            id="prompt-search"
            type="search"
            value={search()}
            onInput={(e) => setSearch(e.target.value)}
            class="border-tmauve/25 bg-tcreme/40 text-tslate placeholder:text-tdeepgray/60 focus:border-tmauve focus:outline-tmauve block w-full rounded-2xl border p-3 pl-12 text-base focus:outline-2 focus:outline-offset-2"
            placeholder="Try gratitude, change, or connection…"
            aria-controls="prompt-results"
          />
        </div>
        <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
          <h2 class="eyebrow text-tpink-tint">Explore a theme</h2>
          <Show when={search()}>
            <button
              onClick={() => setSearch("")}
              type="button"
              class="text-tpink-tint focus-visible:outline-tpink-tint text-sm underline underline-offset-4 hover:no-underline focus-visible:outline-2 focus-visible:outline-offset-2">
              Clear search
            </button>
          </Show>
        </div>
        <div class="mt-2 flex max-h-48 flex-wrap gap-2 overflow-y-auto p-1">
          <button
            type="button"
            onClick={() => setSearch("")}
            aria-pressed={search() === ""}
            class="focus-visible:outline-tpink-tint rounded-full border px-3.5 py-2 text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2"
            classList={{
              "border-tmauve bg-tmauve text-white": search() === "",
              "border-tmauve/15 bg-tcreme/60 text-tdeepgray hover:border-tmauve/50 hover:bg-tmauve/10":
                search() !== "",
            }}>
            All prompts
          </button>
          <For each={tags()}>
            {(tag) => (
              <Tag onClick={setSearch} tag={tag} selected={search() === tag} />
            )}
          </For>
        </div>
      </section>
      <div class="mt-6 mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 class="text-tslate text-2xl font-semibold tracking-tight">
          Prompts to explore
        </h2>
        <p
          class="text-tdeepgray max-w-full text-sm [overflow-wrap:anywhere]"
          role="status">
          {items().length} {items().length === 1 ? "prompt" : "prompts"}
          {search() ? ` matching “${search()}”` : " to choose from"}
        </p>
      </div>
      <ul id="prompt-results" class="grid gap-4 md:grid-cols-2">
        <For each={items()}>
          {(item) => (
            <Prompt
              prompt={item.prompt}
              tagClick={setSearch}
              tags={item.tags}
              search={search()}
            />
          )}
        </For>
      </ul>
      <Show when={items().length === 0}>
        <div class="border-tmauve/20 bg-tmauve/5 rounded-3xl border border-dashed px-5 py-8 text-center">
          <h3 class="text-tslate text-xl font-semibold">
            {data().length === 0
              ? "More conversations to come"
              : "No prompts found"}
          </h3>
          <p class="text-tdeepgray mt-3 text-sm leading-relaxed">
            {data().length === 0
              ? "Check back soon for prompts from our Keepers."
              : "Try a different word or choose a theme above."}
          </p>
        </div>
      </Show>
    </div>
  )
}

PromptSearch.tagName = "t-promptsearch"
PromptSearch.propsDefault = {
  dataid: "prompt-search-data",
}
export default PromptSearch
