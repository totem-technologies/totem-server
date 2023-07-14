import dataclasses

import faker
from django.shortcuts import render

fake = faker.Faker()


@dataclasses.dataclass
class Circle:
    title: str
    subtitle: str
    tags: list[str]
    description: str
    image_url: str
    author: str
    author_url: str
    date_modified: str
    published: bool
    author_image_url: str
    slug: str
    pk: int
    price: str
    type: str
    datetime: str
    duration: str


def detail(request, slug):
    circle = Circle(
        title=fake.sentence(),
        subtitle=fake.sentence(),
        tags=["tag1", "tag2", "tag3"],
        description=fake.paragraph(100),
        image_url="https://picsum.photos/seed/picsum/200/300",
        author=fake.name(),
        author_url="https://picsum.photos/seed/picsum/200/300",
        date_modified="2021-01-01",
        published=True,
        author_image_url="https://picsum.photos/seed/picsum/300",
        slug="circle-slug",
        pk=1,
        price="Free",
        type="Circle",
        datetime="2021-01-01",
        duration="1 hour",
    )
    return render(request, "circles/detail.html", {"object": circle})
