from django.views.generic import DetailView, ListView
from .models import BlogPost

class BlogPostDetailView(DetailView):
    model = BlogPost
    template_name = "blog/detail.html"
    context_object_name = "post"

class BlogPostListView(ListView):
    model = BlogPost
    template_name = "blog/list.html"
    context_object_name = "posts"
