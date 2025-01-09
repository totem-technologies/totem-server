import { convertISOToHHMM, getDateFromISOString } from "@/libs/time"
import { getTimeZone } from "@/libs/timezone"
function AddToCalendarButton(props: {
  name: string
  calLink: string
  start: string
  durationMinutes: number
}) {
  // let debug = "true"
  const startDate = () => getDateFromISOString(props.start)
  const startTime = () => convertISOToHHMM(props.start)

  // Add duration to end date
  const endDateObj = () => new Date(props.start)
  endDateObj().setMinutes(endDateObj().getMinutes() + props.durationMinutes)
  const endDate = () => getDateFromISOString(endDateObj().toISOString())
  const endTime = () => convertISOToHHMM(endDateObj().toISOString())

  // Sanitize strings
  const name = () => `${props.name}`.replaceAll('"', "")
  const calLink = () => `${props.calLink}?r=cal_link`.replaceAll('"', "")

  // console.log(props)
  const debug = globalThis.TOTEM_DATA.debug ? "true" : "false"
  const el = `<add-to-calendar-button
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
      timeZone="${getTimeZone()}"></add-to-calendar-button>`
  // eslint-disable-next-line solid/no-innerhtml
  return <div innerHTML={el} />
}

export default AddToCalendarButton
