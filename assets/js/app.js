import emailSpellChecker from './emailSpellCheck'

dismiss_alert = function (e) {
    e.closest('.alert-dismissible').remove()
}

// initialize tooltips on DOM ready
document.addEventListener('DOMContentLoaded', function () {})

// Timezone settings
const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone // e.g. "America/New_York"
document.cookie = `totem_timezone=${timezone}; SameSite=Strict`
console.log('great success!')

window.addEventListener('DOMContentLoaded', () => {
    emailSpellChecker()
})
