export const nthNumber = (number: number) => {
  if (number > 3 && number < 21) return "th"
  switch (number % 10) {
    case 1:
      return "st"
    case 2:
      return "nd"
    case 3:
      return "rd"
    default:
      return "th"
  }
}

export function timestampToDateString(timestamp: string) {
  // Date in the form of "Tuesday, May 1st"
  const date = new Date(timestamp).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  })
  return date + nthNumber(new Date(timestamp).getDate())
}

export function timestampToTimeString(timestamp: string) {
  // Convert timestamp to HH:MM AM/PM Timezone
  return new Date(timestamp).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  })
}

export function convertISOToHHMM(isoString: string) {
  // Parse the ISO string into a Date object
  const date = new Date(isoString)

  // Extract hours and minutes, adding leading zeros if necessary
  const hours = date.getHours().toString().padStart(2, "0")
  const minutes = date.getMinutes().toString().padStart(2, "0")

  // Return the time in HH:MM format
  return `${hours}:${minutes}`
}

export function getDateFromISOString(isoString: string) {
  // Parse the ISO string into a Date object
  const date = new Date(isoString)

  // Extract year, month, and day, adding leading zeros to month and day if necessary
  const year = date.getFullYear()
  const month = (date.getMonth() + 1).toString().padStart(2, "0") // Months are zero-based, so add 1
  const day = date.getDate().toString().padStart(2, "0")

  // Return the date in YYYY-MM-DD format
  return `${year}-${month}-${day}`
}
