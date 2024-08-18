declare module "*.jsx" {
  const _: () => unknown
  export default _
}

declare namespace JSX {
  interface IntrinsicElements {
    "add-to-calendar-button": unknown
  }
}

// add TOTEM_DATA to window
declare interface Window {
  TOTEM_DATA: {
    debug: boolean
    csrf_token: string
    is_authenticated: boolean
    reload_on_login: boolean
  }
}
