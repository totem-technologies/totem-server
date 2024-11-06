import { domToWebp } from "modern-screenshot"

let imgsDivs = document.querySelectorAll("[data-img]>div")

imgsDivs.forEach((imgDiv) => {
  console.log(imgDiv)
  domToWebp(imgDiv, {
    scale: 2,
  }).then((dataUrl) => {
    // attach dataUrl to the button imgDiv so that the image downloads when the button is clicked

    imgDiv.addEventListener("click", () => {
      const link = document.createElement("a")
      link.href = dataUrl
      link.download = "image.webp"
      console.log(link)
      link.click()
    })
  })
})
