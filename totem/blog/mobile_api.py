from typing import List, Optional

from django.shortcuts import get_object_or_404
from ninja import ModelSchema, Router
from ninja.pagination import paginate

from totem.users.schemas import PublicUserSchema

from .models import BlogPost


class BlogPostSchema(ModelSchema):
    author: Optional[PublicUserSchema] = None
    header_image_url: Optional[str] = None
    content_html: Optional[str] = None

    @staticmethod
    def resolve_header_image_url(obj) -> Optional[str]:
        if obj.header_image and hasattr(obj.header_image, "url"):
            return obj.header_image.url
        return None

    class Meta:
        model = BlogPost
        fields = ["title", "subtitle", "date_published", "slug", "author", "publish", "read_time", "summary"]


class BlogPostListSchema(ModelSchema):
    author: Optional[PublicUserSchema] = None
    header_image_url: Optional[str] = None

    @staticmethod
    def resolve_header_image_url(obj: BlogPost) -> Optional[str]:
        if obj.header_image and hasattr(obj.header_image, "url"):
            return obj.header_image.url
        return None

    class Meta:
        model = BlogPost
        fields = ["title", "subtitle", "date_published", "slug", "author", "publish", "read_time", "summary"]


blog_router = Router()


@blog_router.get("/posts", response={200: List[BlogPostListSchema]}, tags=["blog"], url_name="list_posts")
@paginate
def list_posts(request):
    """List all blog posts"""

    if request.user.is_staff:
        posts = BlogPost.objects.all()
    else:
        posts = BlogPost.objects.filter(publish=True)
    return posts.order_by("-date_published").select_related("author")


@blog_router.get("/post/{slug}", response=BlogPostSchema, tags=["blog"], url_name="get_post")
def post(request, slug: str):
    if request.user.is_staff:
        post = BlogPost.objects.select_related("author")
    else:
        post = BlogPost.objects.select_related("author").filter(publish=True)

    return get_object_or_404(post, slug=slug)
