// Create a BroadcastChannel that will be used to communicate between the login page and the main page.
// When the user logs in, send a message to all tabs that are listening to reload the page.

const CHANNEL_NAME = "login"
const LOGIN_MESSAGE = "logged_in"

function init() {
  const channel = new BroadcastChannel(CHANNEL_NAME)
  channel.onmessage = (event) => {
    if (
      window.TOTEM_DATA.reload_on_login === true &&
      event.data === LOGIN_MESSAGE
    ) {
      location.reload()
    }
  }
  if (window.TOTEM_DATA.is_authenticated === true) {
    channel.postMessage(LOGIN_MESSAGE)
  }
}

export default init
