declare module "*.jsx" {
  const _: () => unknown
  export default _
}

declare namespace JSX {
  interface IntrinsicElements {
    "add-to-calendar-button": unknown
  }
}

declare global {
  // Exposed by the self-hosted add-to-calendar-button bundle (js/atcb.min.js)
  function atcb_action(
    config: import("add-to-calendar-button").ATCBActionEventConfig,
    triggerElement?: HTMLElement,
    keyboardTrigger?: boolean
  ): Promise<string>
  function _AutofillCallbackHandler(): void
  var TOTEM_DATA: {
    debug: boolean
    is_authenticated: boolean
    reload_on_login: boolean
  }
}

export {}
