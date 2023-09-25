// document.addEventListener("alpine:init", () => {
//   let opts = { outOfOrder: false }
//   let uf = new uFuzzy(opts)
//   let data = JSON.parse(document.getElementById("search_data").textContent)
//   let haystack = data.map((r) => `${r.prompt} ${r.tags.join(" ")}`)
//   let tags = [...new Set(data.map((r) => r.tags).flat())].sort()
// })

export default () => ({
  search: "",
  items: [],
  tags: [],
  init() {
    let opts = { outOfOrder: false }
    this.uf = new uFuzzy(opts)
    this.items = data = JSON.parse(
      document.getElementById("search_data").textContent
    )
    this.haystack = data.map((r) => `${r.prompt} ${r.tags.join(" ")}`)
    this.tags = [...new Set(data.map((r) => r.tags).flat())].sort()
  },
  get filteredItems() {
    if (this.search === "") {
      return this.items
    }
    let [idxs, info, order] = this.uf.search(this.haystack, this.search)
    console.log(this.search)
    if (order) {
      return order.map((i) => idxs.map((i) => this.items[i])[i])
    }
    return this.items
  },
})
