import { totemCirclesApiUpcomingEvents } from "@/client"
import Calendar from "@rnwonder/solid-date-picker/calendar"
import "@rnwonder/solid-date-picker/dist/style.css"
import { createQuery } from "@tanstack/solid-query"
import { createSignal, JSX, Suspense } from "solid-js"
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
        <div class="spinner-border" role="status">
          <span class="loading loading-spinner loading-lg"></span>
        </div>
      </div>
    </DetailBox>
  )
}

const EventCalendar = (props: { spaceid: string; eventid: string }) => {
  const [month, setMonth] = createSignal(new Date().getMonth() + 1)
  const [year, setYear] = createSignal(new Date().getFullYear())
  const query = createQuery(() => ({
    queryKey: ["eventUpcoming"],
    queryFn: async () => {
      return totemCirclesApiUpcomingEvents({
        spaceSlug: props.spaceid,
        month: month(),
        year: year(),
      })
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
            query.refetch()
          }}
          onYearChange={(data) => {
            setYear(data)
            query.refetch()
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
