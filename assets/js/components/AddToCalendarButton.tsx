import type { ATCBActionEventConfig } from "add-to-calendar-button"
import { convertISOToHHMM, getDateFromISOString } from "@/libs/time"
import { getTimeZone } from "@/libs/timezone"
import Icon from "./icons"

function AddToCalendarButton(props: {
  name: string
  calLink: string
  start: string
  durationMinutes: number
  compact?: boolean
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
      class={
        props.compact
          ? "btn btn-outline btn-sm shrink-0"
          : "btn btn-outline w-full"
      }
      onClick={(e) => void globalThis.atcb_action(config(), e.currentTarget)}>
      <Icon name="calendar" size={props.compact ? 16 : 20} />
      Add to Calendar
    </button>
  )
}

// Web-component adapter: lowercase attribute names, string-typed values.
// Usage in templates:
// <t-add-to-calendar name="..." callink="..." start="..." duration="60" compact="true">
export function AddToCalendarElement(props: {
  name: string
  callink: string
  start: string
  duration: number | string
  compact: string | boolean
}) {
  return (
    <AddToCalendarButton
      name={props.name}
      calLink={props.callink}
      start={props.start}
      durationMinutes={Number(props.duration) || 60}
      compact={props.compact === true || props.compact === "true"}
    />
  )
}

AddToCalendarElement.tagName = "t-add-to-calendar"
AddToCalendarElement.propsDefault = {
  name: "",
  callink: "",
  start: "",
  duration: 60,
  compact: "false",
}

export default AddToCalendarButton
