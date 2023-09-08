from totem.utils.templatetags.avatar import avatar_marble

gold = {
    "classes": "",
    "size": 80,
    "SIZE": 80,
    "SIZED2": 40.0,
    "RX": 160,
    "name": "868ce1c742d4451efea8",
    "properties": [
        {"color": "#FF2135", "translateX": 5.4, "translateY": 5.43, "scale": 1.5, "rotate": 244.2},
        {"color": "#12E895", "translateX": 0.6, "translateY": 0.57, "scale": 1.2, "rotate": 25.7},
        {"color": "#1AAACF", "translateX": 0.3, "translateY": 0.3, "scale": 1.2, "rotate": 13.3},
    ],
    "mask_id": "mask_600517148618568300772719",
    "title": False,
}


def test_avatar():
    assert (
        avatar_marble(
            name="868ce1c742d4451efea8",
            size=80,
            square=False,
        )
        == gold
    )
