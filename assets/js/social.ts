import { domToPng } from "modern-screenshot"

const imgsDivs = document.querySelectorAll("[data-img]>div")

for (const imgDiv of imgsDivs) {
  // attach dataUrl to the button imgDiv so that the image downloads when the button is clicked
  imgDiv.addEventListener("click", async () => {
    const dataUrl = await domToPng(imgDiv, {
      scale: 2,
      fetch: {
        requestInit: {
          cache: "no-cache",
        },
      },
    })
    // generate filename from current URL
    const slug = window.location.pathname
      .split("/")
      .slice(-2)[0]
      .replace("/", "-")
    const link = document.createElement("a")
    link.href = dataUrl
    link.download = `${slug}.png`
    console.log(link)
    link.click()
  })
}
