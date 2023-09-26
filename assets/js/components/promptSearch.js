import { useEffect, useState } from "preact/hooks"

function Tag(props) {
  return (
    <button
      onClick={() => props.onClick(props.tag)}
      type="button"
      class="mr-2 mt-1 inline-flex items-center rounded-full bg-tyellow px-3 py-1 text-xs font-medium leading-4 text-gray-700"
    >
      {props.tag}
    </button>
  )
}

function Prompt(props) {
  const tags = props.tags.map((tag) => (
    <Tag onClick={props.tagClick} tag={tag}></Tag>
  ))
  return (
    <li class="mb-2 rounded-lg border-2 bg-white px-4 py-2">
      <div class="pb-3">{props.prompt}</div>
      {tags}
    </li>
  )
}

function PromptSearch(props) {
  const [search, setSearch] = useState("")
  const [items, setItems] = useState([])
  const [tags, setTags] = useState([])
  const [uf, setUf] = useState(null)
  const [haystack, setHaystack] = useState([])
  const [data, setData] = useState([])
  useEffect(() => {
    let opts = { outOfOrder: false }
    let uf = new uFuzzy(opts)
    let data = JSON.parse(document.getElementById(props.dataid).textContent)
    let haystack = data.map((r) => `${r.prompt} ${r.tags.join(" ")}`)
    let tags = [...new Set(data.map((r) => r.tags).flat())].sort()
    setUf(uf)
    setHaystack(haystack)
    setTags(tags)
    setData(data)
    setItems(data)
  }, [])
  function updateSearch(search) {
    if (search === "") {
      setItems(data)
    } else {
      let [idxs, info, order] = uf.search(haystack, search)
      if (order) {
        setItems(order.map((i) => idxs.map((i) => data[i])[i]))
      }
    }
    setSearch(search)
  }
  const tagsList = tags.map((tag) => (
    <Tag onClick={updateSearch} tag={tag}></Tag>
  ))
  const prompts = items.map((item) => (
    <Prompt
      prompt={item.prompt}
      tagClick={updateSearch}
      tags={item.tags}
    ></Prompt>
  ))
  return (
    <div>
      <div class="relative py-5">
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
            ></path>
          </svg>
        </div>
        <input
          type="search"
          value={search}
          onChange={(e) => updateSearch(e.target.value)}
          class="block w-full rounded-lg border border-gray-300 bg-gray-50 p-4 pl-10 text-sm text-gray-900 focus:border-blue-500 focus:ring-blue-500 "
          placeholder="Search prompts..."
          required
        />
      </div>
      {tagsList}
      <ul class="pt-10">{prompts}</ul>
    </div>
  )
}

PromptSearch.tagName = "t-promptsearch"

export default PromptSearch
