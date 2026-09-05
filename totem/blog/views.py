from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q, QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.generic import DetailView, ListView

from totem.utils.img_gen import BlogImageParams, generate_blog_image

from .models import BlogPost


def _visible_posts(request: HttpRequest) -> QuerySet[BlogPost]:
    """Posts this visitor may see: published ones, plus drafts for staff."""
    qs = BlogPost.objects.all()
    if request.user.is_staff:
        return qs
    return qs.filter(publish=True)


class BlogPostDetailView(DetailView):  # pyright: ignore[reportMissingTypeArgument]
    model = BlogPost
    template_name = "blog/detail.html"
    context_object_name = "post"

    def get_queryset(self):
        return _visible_posts(self.request).select_related("author")

    def get_object(self, queryset=None):
        post = super().get_object(queryset)
        if not post.publish and not self.request.user.is_staff:
            raise Http404("Post not found")
        return post

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        post: BlogPost = context["post"]
        # Posts share timestamps often enough (bulk imports, tests) that the
        # primary key has to break ties, or neighbours would be skipped.
        posts = _visible_posts(self.request).only("slug", "title", "date_published", "publish")
        context["older_post"] = (
            posts.filter(
                Q(date_published__lt=post.date_published) | Q(date_published=post.date_published, pk__lt=post.pk)
            )
            .order_by("-date_published", "-pk")
            .first()
        )
        context["newer_post"] = (
            posts.filter(
                Q(date_published__gt=post.date_published) | Q(date_published=post.date_published, pk__gt=post.pk)
            )
            .order_by("date_published", "pk")
            .first()
        )
        return context


def archive(request: HttpRequest):
    """Every post on one page, so each is one click from the blog index."""
    posts = (
        _visible_posts(request)
        .select_related("author")
        .only(
            "slug",
            "title",
            "date_published",
            "publish",
            "author__name",
            "author__profile_image",
            "author__profile_avatar_seed",
            "author__profile_avatar_type",
        )
    )
    return render(request, "blog/archive.html", {"posts": posts})


class BlogPostListView(ListView):  # pyright: ignore[reportMissingTypeArgument]
    model = BlogPost
    template_name = "blog/list.html"
    context_object_name = "posts"
    paginate_by = 12

    def get_queryset(self):
        return _visible_posts(self.request).select_related("author")


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
    background_url = f"{settings.BASE_DIR}/totem/static/images/spaces/default-bg.jpg"
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

    image = _make_social_img_post(post, image_size, show_new)
    response = HttpResponse(content_type="image/jpeg")
    response["Cache-Control"] = "max-age=600"
    response.write(image.to_jpeg())
    return response
