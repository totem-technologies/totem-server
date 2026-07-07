import type { ATCBActionEventConfig } from "add-to-calendar-button"
import { convertISOToHHMM, getDateFromISOString } from "@/libs/time"
import { getTimeZone } from "@/libs/timezone"
import Icon from "./icons"

function AddToCalendarButton(props: {
  name: string
  calLink: string
  start: string
  durationMinutes: number
}) {
  const config = (): ATCBActionEventConfig => {
    const end = new Date(props.start)
    end.setMinutes(end.getMinutes() + props.durationMinutes)
    return {
      name: `[Totem] ${props.name}`,
      options: ["Apple", "Google", "Outlook.com"],
      location: `${props.calLink}?r=cal_link`,
      startDate: getDateFromISOString(props.start),
      endDate: getDateFromISOString(end.toISOString()),
      startTime: convertISOToHHMM(props.start),
      endTime: convertISOToHHMM(end.toISOString()),
      timeZone: getTimeZone(),
      listStyle: "overlay",
      hideBranding: true,
      debug: globalThis.TOTEM_DATA.debug,
    }
  }
  return (
    <button
      type="button"
      class="btn btn-outline w-full"
      onClick={(e) => void globalThis.atcb_action(config(), e.currentTarget)}>
      <Icon name="calendar" />
      Add to Calendar
    </button>
  )
}

export default AddToCalendarButton
