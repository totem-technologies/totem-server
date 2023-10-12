from totem.utils.templatetags.avatar import avatar_marble

gold = {
    "RX": 160,
    "SIZE": 80,
    "SIZED2": 40.0,
    "mask_id": "mask_948225242526584141959851",
    "properties": [
        {"color": "#524235", "rotate": 92.6, "scale": 1.3, "translateX": 2.1, "translateY": 2.06},
        {"color": "#9A8570", "rotate": 221.8, "scale": 1.4, "translateX": 4.9, "translateY": 4.93},
        {"color": "#9A8570", "rotate": 30.6, "scale": 1.2, "translateX": 0.7, "translateY": 0.68},
    ],
    "salt": "868ce1c742d4451efea8868ce1c742d4451efea8",
    "size": 80,
}


def test_avatar():
    assert (
        avatar_marble(
            salt="868ce1c742d4451efea8868ce1c742d4451efea8",
            size=80,
        )
        == gold
    )
