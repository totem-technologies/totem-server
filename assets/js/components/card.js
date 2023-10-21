function Card(props) {
  const imgeUrl = props.image ? `url(${props.image})` : ""
  backgroundImageStyle = {
    backgroundImage: `linear-gradient(185deg, rgba(196, 204, 255, 0.52), rgba(117, 19, 93, 0.73)), ${imgeUrl}`,
    backgroundSize: "cover",
    backgroundPosition: "center",
    backgroundRepeat: "no-repeat",
    height: "150px",
  }

  const image = (
    <a href={props.href}>
      <div
        class="relative flex flex-col rounded-t-3xl p-5 pb-2"
        style={backgroundImageStyle}
      >
        <div class="flex flex-1 items-center">
          <h5 class="mb-2 line-clamp-2 overflow-ellipsis break-words text-2xl font-bold tracking-tight text-white">
            {props.title}
          </h5>
        </div>
        <div class="flex items-end justify-between ">
          <div class="pr-4">
            <p class="mb-3 font-normal text-white">{props.description}</p>
          </div>
          <div>
            <div class="w-[50px] rounded-full">
              <a href={props.href}>{props.avatar}</a>
            </div>
          </div>
        </div>
      </div>
    </a>
  )
  return (
    <div class="relative max-w-[300px] overflow-clip rounded-3xl border border-gray-200 bg-white shadow transition-shadow hover:shadow-xl">
      {image}
      <div class="p-5">
        <div class="flex flex-col">
          <p class="mb-3 font-normal text-gray-700 ">{props.start}</p>
          <a
            href={props.href}
            class="btn btn-primary btn-sm inline-flex items-center"
          >
            {props.buttonText}
            <svg
              class="ml-2 h-3.5 w-3.5"
              aria-hidden="true"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 14 10"
            >
              <path
                stroke="currentColor"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M1 5h12m0 0L9 1m4 4L9 9"
              />
            </svg>
          </a>
        </div>
      </div>
    </div>
  )
}

Card.tagName = "t-card"
export default Card
