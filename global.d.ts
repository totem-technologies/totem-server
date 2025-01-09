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
  function dismiss_alert(e: HTMLElement): void
  function _AutofillCallbackHandler(): void
  function copyTextToClipboard(element: HTMLElement): void
  var TOTEM_DATA: {
    debug: boolean
    csrf_token: string
    is_authenticated: boolean
    reload_on_login: boolean
  }
}

export {}
