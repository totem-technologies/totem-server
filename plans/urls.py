from django.urls import path
from . import views

app_name = "films"

urlpatterns = [
    path("", views.PlanListView.as_view(), name="all"),
    path("plans/<int:pk>/", views.PlanDetailView.as_view(), name="detail"),
    # path("plans/create/", views.PlanCreateView.as_view(), name="create"),
    # path("plans/<int:pk>/update/", views.PlanUpdateView.as_view(), name="update"),
    # path("plans/<int:pk>/delete/", views.PlanDeleteView.as_view(), name="delete"),
]
