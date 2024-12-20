from .. import img_gen


def test_cache_key():
    params = img_gen.ImageParams(
        background_path="tests/img_gen/background.jpg",
        author_img_path="tests/img_gen/me.jpg",
        author_name="Bo",
        title="The Addicted Brain",
        subtitle="Rediscovering Moderation",
        day="Jan 10 @ 3:00am PST",
        time_est="10:00 pm EST",
        time_pst="10:00 pm PST",
        width=1080,
        height=1080,
        # width=1024,
        # height=512,
    )
    gold = "d21b0fb33afc62a687abc8a491699d885647b4a67ee138c4afd0a679d929db8a"
    assert params.cache_key() == gold
    params.width = 200
    assert params.cache_key() != gold


def test_gen():
    import os

    folder_path = os.path.dirname(os.path.realpath(__file__))
    params = img_gen.ImageParams(
        background_path=f"{folder_path}/img_gen/background.jpg",
        author_img_path=f"{folder_path}/img_gen/me.jpg",
        author_name="Bo",
        title="The Addicted Brain",
        subtitle="Rediscovering Moderation",
        day="Jan 10 @ 3:00am PST",
        time_est="10:00 pm EST",
        time_pst="10:00 pm PST",
        width=1080,
        height=1080,
        # width=1024,
        # height=512,
    )
    image = img_gen.generate_image(params)
    assert image
