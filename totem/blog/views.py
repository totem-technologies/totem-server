from dataclasses import dataclass
from io import BytesIO

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.generic import DetailView, ListView

from totem.utils.img_gen import BlogImageParams, generate_blog_image

from .models import BlogPost


class BlogPostDetailView(DetailView):  # pyright: ignore[reportMissingTypeArgument]
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


class BlogPostListView(ListView):  # pyright: ignore[reportMissingTypeArgument]
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
    if not post.publish and not request.user.is_staff:  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        raise Http404("Post not found")
    return render(request, "blog/social.html", {"post": post})


def _make_social_img_post(post: BlogPost, image_size: SocialImage, show_new: bool):
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

    params = BlogImageParams(
        background_path=background_url,
        author_img_path=author_profile_url,
        author_name=author_name,
        title=post.title,
        width=image_size.width,
        height=image_size.height,
        show_new=show_new,
    )
    return generate_blog_image(params)


def post_social_img(request: HttpRequest, slug: str, image_format: str):
    image_size = {
        "square": SocialImage(height=1080, width=1080),
        "2to1": SocialImage(width=1280, height=640),
        "4to5": SocialImage(width=1080, height=1350),
    }.get(image_format)
    show_new = request.GET.get("new", "true") == "true"
    if not image_size:
        raise Http404("Image format not found")

    try:
        post = BlogPost.objects.get(slug=slug)
    except BlogPost.DoesNotExist:
        raise Http404("Post not found")
    if not post.publish and not request.user.is_staff:  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
        raise Http404("Post not found")

    buffer = BytesIO()
    _make_social_img_post(post, image_size, show_new).save(buffer, "JPEG", optimize=True)
    response = HttpResponse(content_type="image/jpeg")
    response["Cache-Control"] = "max-age=600"
    response.write(buffer.getvalue())
    return response
