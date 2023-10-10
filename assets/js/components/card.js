function Card(props) {
  backgroundImageStyle = {
    backgroundImage: `linear-gradient(185deg, rgba(196, 204, 255, 0.52), rgba(117, 19, 93, 0.73)), url(${props.image})`,
    backgroundSize: "cover",
    backgroundPosition: "center",
    backgroundRepeat: "no-repeat",
    height: "150px",
  }
  const avatar = props.avatar ? (
    <div class="absolute left-1/2 top-1/2 w-[100px] -translate-x-1/2 -translate-y-1/2  rounded-full bg-tcreme p-0.5">
      <a class="" href={props.href}>
        {props.avatar}
      </a>
    </div>
  ) : null
  const image = props.image ? (
    <a href={props.href}>
      <div class="relative rounded-t-3xl" style={backgroundImageStyle}>
        {avatar}
      </div>
    </a>
  ) : null
  return (
    <div class="relative max-w-[300px] rounded-3xl border border-gray-200 bg-white shadow ">
      {image}
      <div class="p-5">
        <a href={props.href}>
          <h5 class="mb-2 text-2xl font-bold tracking-tight text-gray-900">
            {props.title}
          </h5>
        </a>
        <p class="mb-3 font-normal text-gray-700 ">{props.description}</p>
        <a href={props.href} class="btn-primary inline-flex items-center">
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
  )
}

Card.tagName = "t-card"
export default Card
