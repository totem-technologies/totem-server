import type { ATCBActionEventConfig } from "add-to-calendar-button"
import { convertISOToHHMM, getDateFromISOString } from "@/libs/time"
import { getTimeZone } from "@/libs/timezone"
import Icon from "./icons"

// block: fills a stacked layout (event sidebar); inline: sits in a row of
// actions (dashboard hero); compact: small inline (dashboard session rows)
const variantClasses = {
  block: "btn btn-outline w-full",
  inline: "btn btn-outline shrink-0",
  compact: "btn btn-outline btn-sm shrink-0",
}

function AddToCalendarButton(props: {
  name: string
  calLink: string
  start: string
  durationMinutes: number
  variant?: keyof typeof variantClasses
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
      // "overlay" positions off the trigger's flow position, which breaks
      // inside our centered full-width layout (off-screen on mobile).
      listStyle: "modal",
      hideBranding: true,
      debug: globalThis.TOTEM_DATA.debug,
    }
  }
  return (
    <button
      type="button"
      class={variantClasses[props.variant ?? "block"]}
      onClick={(e) => void globalThis.atcb_action(config(), e.currentTarget)}>
      <Icon name="calendar" size={props.variant === "compact" ? 16 : 20} />
      Add to Calendar
    </button>
  )
}

export default AddToCalendarButton
