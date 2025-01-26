from django.http import Http404
from django.views.generic import DetailView, ListView

from .models import BlogPost


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
