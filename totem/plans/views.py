from django.urls import reverse_lazy
from django.views import View
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView

from .models import CirclePlan


class PlanBaseView(View):
    model = CirclePlan
    fields = "__all__"
    success_url = reverse_lazy("plans:all")


class PlanListView(PlanBaseView, ListView):
    """List self-guided Space plans."""

    template_name = "plans/spaceplan_list.html"


class PlanDetailView(PlanBaseView, DetailView):
    """Display a self-guided Space plan."""

    template_name = "plans/spaceplan_detail.html"


class PlanCreateView(PlanBaseView, CreateView):
    """View to create a new film"""


class PlanUpdateView(PlanBaseView, UpdateView):
    """View to update a film"""


class PlanDeleteView(PlanBaseView, DeleteView):
    """View to delete a film"""
