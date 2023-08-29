from totem.utils.templatetags.avatar import avatar_marble

gold = """
<svg class="" viewBox="0 0 80 80" fill="none" role="img" xmlns="http://www.w3.org/2000/svg" width="80" height="80"><mask id="mask_600517148618568300772719" maskUnits="userSpaceOnUse" x="0" y="0" width="80" height="80"><rect width="80" height="80" rx="160" fill="#FFFFFF"/></mask><g mask="url(#mask_600517148618568300772719)"><rect width="80" height="80" fill="#FF2135"/><path filter="url(#prefix__filter0_f)" d="M32.414 59.35L50.376 70.5H72.5v-71H33.728L26.5 13.381l19.057 27.08L32.414 59.35z" fill="#12E895" transform="translate(0.6 0.57) rotate(25.7 40.0 40.0) scale(1.2)" /><path filter="url(#prefix__filter0_f)" style="mix-blend-mode:overlay" d="M22.216 24L0 46.75l14.108 38.129L78 86l-3.081-59.276-22.378 4.005 12.972 20.186-23.35 27.395L22.215 24z" fill="#1AAACF" transform="translate(0.3 0.3) rotate(13.3 40.0 40.0) scale(1.2)" /></g><defs><filter id="prefix__filter0_f" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB"><feFlood flood-opacity="0" result="BackgroundImageFix"></feFlood><feBlend in="SourceGraphic" in2="BackgroundImageFix" result="shape"></feBlend><feGaussianBlur stdDeviation="7" result="effect1_foregroundBlur"></feGaussianBlur></filter></defs></svg>
"""


def test_avatar():
    assert (
        avatar_marble(
            name="868ce1c742d4451efea8",
            size=80,
            square=False,
        ).strip()
        == gold.strip()
    )
