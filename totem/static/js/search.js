(() => {
  const data = JSON.parse(document.getElementById("search_data").textContent);
  const template = document.getElementById("prompttemplate").innerHTML;
  let haystack = data.map((r) => `${r.prompt}¦${r.tags}`);
  let opts = {};
  let uf = new uFuzzy(opts);

  function render(results) {
    document.getElementById("searchresults").innerHTML = "";
    var finalhtml = "";
    for (let i = 0; i < results.length; i++) {
      let prompt = results[i];
      let html = template
        .replace(/{prompt}/g, prompt.prompt)
        .replace(/{tags}/g, prompt.tags);
      finalhtml += html;
    }
    document.getElementById("searchresults").innerHTML += finalhtml;
  }

  function getTags() {
    let tags = [];
    for (let i = 0; i < data.length; i++) {
      let prompt = data[i];
      tags.push(prompt.tags);
    }
    return [...new Set(tags)];
  }

  window.searchnow = function () {
    let needle = document.getElementById("search").value;
    let [idxs, info, order] = uf.search(haystack, needle);
    if (order) {
      results = order.map((i) => data[i]);
      render(results);
    } else {
      render(data);
    }
  };
  render(data);
})();
