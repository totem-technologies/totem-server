import { domToPng } from "modern-screenshot"

const imgsDivs = document.querySelectorAll("[data-img]>div")

for (const imgDiv of imgsDivs) {
  console.log(imgDiv)
  domToPng(imgDiv, {
    scale: 2,
  }).then((dataUrl) => {
    // generate filename from current URL
    const slug = window.location.pathname
      .split("/")
      .slice(-2)[0]
      .replace("/", "-")
    // attach dataUrl to the button imgDiv so that the image downloads when the button is clicked
    imgDiv.addEventListener("click", () => {
      const link = document.createElement("a")
      link.href = dataUrl
      link.download = `${slug}.png`
      console.log(link)
      link.click()
    })
  })
}
