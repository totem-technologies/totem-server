from io import BytesIO
from dataclasses import dataclass

import pytz
from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.generic import DetailView, ListView

from .models import BlogPost
from totem.circles.img_gen import ImageParams, generate_image


class BlogPostDetailView(DetailView):
    model = BlogPost
    template_name = "blog/detail.html"
    context_object_name = "post"

    def get_queryset(self):
        if self.request.user.is_staff:
            return BlogPost.objects.all()
        return BlogPost.objects.filter(publish=True)

    def get_object(self, queryset=None):
        post = super().get_object(queryset)
        if not post.publish and not self.request.user.is_staff:
            raise Http404("Post not found")
        return post


class BlogPostListView(ListView):
    model = BlogPost
    template_name = "blog/list.html"
    context_object_name = "posts"
    paginate_by = 12

    def get_queryset(self):
        if self.request.user.is_staff:
            return BlogPost.objects.all()
        return BlogPost.objects.filter(publish=True)


@dataclass
class SocialImage:
    height: int
    width: int


def post_social(request: HttpRequest, slug: str):
    try:
        post = BlogPost.objects.get(slug=slug)
    except BlogPost.DoesNotExist:
        raise Http404("Post not found")
    if not post.publish and not request.user.is_staff:
        raise Http404("Post not found")
    return render(request, "blog/social.html", {"post": post})


def _make_social_img_post(post: BlogPost, day: str, time_pst: str, time_est: str, image_size: SocialImage):
    background_url = f"{settings.BASE_DIR}/totem/static/images/circles/default-bg.jpg"
    if post.header_image:
        background_url = post.header_image.url
        if background_url.startswith("/"):
            background_url = f"totem/{background_url}"

    author_profile_url = f"{settings.BASE_DIR}/totem/static/images/default-avatar.jpg"
    author_name = "Totem"
    if post.author:
        if getattr(post.author, "profile_image", None):
            if post.author.profile_image:
                author_profile_url = post.author.profile_image.url
                if author_profile_url.startswith("/"):
                    author_profile_url = f"totem/{author_profile_url}"
        if getattr(post.author, "name", None):
            author_name = post.author.name or author_name

    meta_line = f"By {author_name} • {day}"

    params = ImageParams(
        background_path=background_url,
        author_img_path=author_profile_url,
        author_name=author_name,
        title=post.title,
        subtitle=post.subtitle or "",
        day=day,
        time_pst=time_pst,
        time_est=time_est,
        width=image_size.width,
        height=image_size.height,
        meta_line=meta_line,
        include_avatar=False,
    )
    return generate_image(params)


def post_social_img(request: HttpRequest, slug: str, image_format: str):
    image_size = {
        "square": SocialImage(height=1080, width=1080),
        "2to1": SocialImage(width=1280, height=640),
        "4to5": SocialImage(width=1080, height=1350),
    }.get(image_format)
    if not image_size:
        raise Http404("Image format not found")

    try:
        post = BlogPost.objects.get(slug=slug)
    except BlogPost.DoesNotExist:
        raise Http404("Post not found")
    if not post.publish and not request.user.is_staff:
        raise Http404("Post not found")

    pst = post.date_published.astimezone(pytz.timezone("US/Pacific"))

    day_pst = pst.strftime("%B %d, %Y")

    # For blog social images, omit time labels
    time_pst = ""
    time_est = ""

    buffer = BytesIO()
    _make_social_img_post(post, day_pst, time_pst, time_est, image_size).save(buffer, "JPEG", optimize=True)
    response = HttpResponse(content_type="image/jpeg")
    response["Cache-Control"] = "max-age=600"
    response.write(buffer.getvalue())
    return response
