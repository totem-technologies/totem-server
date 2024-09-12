// Create a BroadcastChannel that will be used to communicate between the login page and the main page.
// When the user logs in, send a message to all tabs that are listening to reload the page.

const CHANNEL_NAME = "login"
const LOGIN_MESSAGE = "logged_in"

function init() {
  // eslint-disable-next-line no-undef
  const channel = new BroadcastChannel(CHANNEL_NAME)
  channel.onmessage = (event) => {
    if (
      globalThis.TOTEM_DATA.reload_on_login === true &&
      event.data === LOGIN_MESSAGE
    ) {
      globalThis.location.reload()
    }
  }
  if (globalThis.TOTEM_DATA.is_authenticated === true) {
    channel.postMessage(LOGIN_MESSAGE)
  }
}

export default init
