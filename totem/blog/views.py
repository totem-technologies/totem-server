from django.views.generic import DetailView
from .models import BlogPost

class BlogPostDetailView(DetailView):
    model = BlogPost
    template_name = "blog/detail.html"
    context_object_name = "post"
