from datetime import datetime
from typing import List, Optional
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Field, FilterSchema, ModelSchema, Router, Schema

from totem.users.models import User
from .models import BlogPost

from ninja import ModelSchema

class AuthorSchema(ModelSchema):
    class Meta:
        model = User
        fields = ["name", "slug"]


class BlogPostSchema(ModelSchema):
    author: Optional[AuthorSchema] = None
    header_image_url: Optional[str] = None

    @staticmethod
    def resolve_header_image_url(obj) -> Optional[str]:
        if obj.header_image and hasattr(obj.header_image, 'url'):
            return obj.header_image.url
        return None

    class Meta:
        model = BlogPost
        fields = ["title", "subtitle", "content", "date_published", "slug", "author", "publish"]

blog_router = Router()

@blog_router.get("/posts", response={200: List[BlogPostSchema]}, tags=["blog"], url_name="list_posts")
def list_posts(request):
    """List all blog posts"""
    
    if request.user.is_staff:
        return BlogPost.objects.all()
    return BlogPost.objects.filter(publish=True)

@blog_router.get("/post/{slug}", response=BlogPostSchema, tags=["blog"], url_name="get_post")
def post(request, slug: str):
    if request.user.is_staff:
        post = get_object_or_404(BlogPost, slug=slug)
    else:
        post = get_object_or_404(BlogPost, slug=slug, publish=True)
    
    return post