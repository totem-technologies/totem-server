function init() {
  console.log("rruleWidget.js")
  document.addEventListener("alpine:init", () => {
    let opts = { outOfOrder: false }
    let uf = new uFuzzy(opts)
    let data = JSON.parse(document.getElementById("search_data").textContent)
    let haystack = data.map((r) => `${r.prompt} ${r.tags.join(" ")}`)
    let tags = [...new Set(data.map((r) => r.tags).flat())].sort()
    Alpine.data("rrule", () => ({
      search: "",
      items: data,
      tags: tags,
      get filteredItems() {
        if (this.search === "") {
          return this.items
        }
        let [idxs, info, order] = uf.search(haystack, this.search)
        console.log(this.search)
        if (order) {
          return order.map((i) => idxs.map((i) => this.items[i])[i])
        }
        return this.items
      },
    }))
  })
}

export default init
