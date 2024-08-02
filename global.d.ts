declare module "*.jsx" {
  var _: () => any
  export default _
}

declare namespace JSX {
  interface IntrinsicElements {
    "add-to-calendar-button": any
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
