import * as Popover from "@radix-ui/react-popover"

var PopoverComponent = (props) => (
  <Popover.Root>
    <Popover.Trigger>{props.trigger}</Popover.Trigger>
    <Popover.Portal>
      <Popover.Content class="rounded-3xl bg-white p-5 leading-none shadow">
        {props.content}
        <Popover.Arrow class="fill-white" />
      </Popover.Content>
    </Popover.Portal>
  </Popover.Root>
)

PopoverComponent.tagName = "t-popover"

export default PopoverComponent
