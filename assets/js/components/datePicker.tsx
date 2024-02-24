import { createSignal } from "solid-js"
import { SimpleDatepicker } from "solid-simple-datepicker"
import "solid-simple-datepicker/styles.css"

const [date, setDate] = createSignal(new Date())

function DatePickerComponent() {
  function localDate() {
    return date().toLocaleDateString()
  }

  const button = (
    <input class="input w-40" value={localDate()} onClick={onClick}></input>
  )
  const style = {
    "--sd-box-shadow": "none",
  } as any
  const popup = (
    <dialog id="edit_date_modal" class="modal">
      <div class="modal-box w-auto">
        <div>
          <SimpleDatepicker
            style={style}
            onFooterDone={close}
            selectedDate={date()}
            onChange={onChange}
          />
        </div>
      </div>
      <form method="dialog" class="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  ) as HTMLDialogElement

  function onClick(e: Event) {
    popup!.showModal()
  }

  function close() {
    popup!.close()
  }

  function onChange(date: Date) {
    console.log(date)
    setDate(date)
  }

  return (
    <>
      {button}
      {popup}
    </>
  )
}

DatePickerComponent.tagName = "t-datepicker"
DatePickerComponent.propsDefault = {
  dataid: "prompt-search-data",
}
export default DatePickerComponent
