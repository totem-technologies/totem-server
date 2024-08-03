import { convertISOToHHMM, getDateFromISOString } from "@/time"

function AddToCalendarButton(props: {
  name: string
  calLink: string
  start: string
  durationMinutes: number
}) {
  // let debug = "true"
  let startDate = () => getDateFromISOString(props.start)
  let startTime = () => convertISOToHHMM(props.start)

  // Add duration to end date
  let endDateObj = () => new Date(props.start)
  endDateObj().setMinutes(endDateObj().getMinutes() + props.durationMinutes)
  let endDate = () => getDateFromISOString(endDateObj().toISOString())
  let endTime = () => convertISOToHHMM(endDateObj().toISOString())

  // Sanitize strings
  let name = () => `${props.name}`.replaceAll('"', "")
  let calLink = () => `${props.calLink}?r=cal_link`.replaceAll('"', "")

  // console.log(props)
  let debug = window.TOTEM_DATA.debug ? "true" : "false"
  let el = `<add-to-calendar-button
      styleLight="--btn-shadow:none; --btn-shadow-hover:none"
      inline
      hideBranding
      buttonStyle="round"
      debug="${debug}"
      listStyle="overlay"
      name="Totem - ${name()}"
      options="'Apple','Google','Outlook.com'"
      location="${calLink()}?r=cal_link"
      startDate="${startDate()}"
      endDate="${endDate()}"
      startTime="${startTime()}"
      endTime="${endTime()}"
      timeZone="UTC"></add-to-calendar-button>`
  // eslint-disable-next-line solid/no-innerhtml
  return <div innerHTML={el} />
}

export default AddToCalendarButton
