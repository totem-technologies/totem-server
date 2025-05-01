import { totemCirclesApiUpcomingEvents } from "@/client"
import Calendar from "@rnwonder/solid-date-picker/calendar"
import "@rnwonder/solid-date-picker/dist/style.css"
import { useQuery } from "@tanstack/solid-query"
import { type JSX, type JSXElement, Suspense, createSignal } from "solid-js"
import "./eventCalendar.css"

function DetailBox(props: { children: JSX.Element }) {
  return (
    <div class="z-20 mt-5 rounded-2xl border border-gray-200 bg-white p-5 md:top-20 md:w-80">
      {props.children}
    </div>
  )
}

function Loading() {
  return (
    <DetailBox>
      <div class="text-center">
        <div class="spinner-border">
          <span class="loading loading-spinner loading-lg" />
        </div>
      </div>
    </DetailBox>
  )
}

const EventCalendar = (props: {
  spaceid: string
  eventid: string
  children?: JSXElement
}) => {
  const [month, setMonth] = createSignal(new Date().getMonth() + 1)
  const [year, setYear] = createSignal(new Date().getFullYear())
  const query = useQuery(() => ({
    queryKey: ["eventUpcoming"],
    queryFn: async () => {
      const response = await totemCirclesApiUpcomingEvents({
        query: {
          space_slug: props.spaceid,
          month: month(),
          year: year(),
        },
      })
      if (response.error) {
        throw new Error(response.error as string)
      }
      return response.data
    },
    throwOnError: true,
  }))

  const events = () =>
    query.data?.map((event) => ({
      title: event.title,
      month: new Date(event.start).getMonth(),
      year: new Date(event.start).getFullYear(),
      day: new Date(event.start).getDate(),
      url: event.url,
      className: props.eventid === event.slug ? "purpleFilledDay" : "purpleDay",
    }))

  //   createEffect(() => {
  //     console.log(query.data)
  //     console.log(month())
  //     console.log(year())
  //   })

  return (
    <Suspense fallback={<Loading />}>
      <DetailBox>
        <Calendar
          customDaysClassName={events()}
          onMonthChange={(data) => {
            setMonth(data + 1)
            void query.refetch()
          }}
          onYearChange={(data) => {
            setYear(data)
            void query.refetch()
          }}
          onChange={(data) => {
            // console.log(data)
            if (data.type === "single") {
              // find the event in the list
              const event = events()?.find((event) => {
                return (
                  event.month === data.selectedDate?.month &&
                  event.year === data.selectedDate?.year &&
                  event.day === data.selectedDate?.day
                )
              })
              if (event) {
                window.location.href = event.url
              }
            }
          }}
        />
      </DetailBox>
    </Suspense>
  )
}

EventCalendar.tagName = "t-eventcalendar"
EventCalendar.propsDefault = {
  spaceid: "",
  eventid: "",
}

export default EventCalendar
