from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.views import defaults as default_views

from totem.api.api import api
from totem.pages.urls import PagesSitemap
from totem.plans.urls import PlansSitemap
from totem.repos.urls import ReposSitemap
from totem.users.views import MagicLoginView

sitemap_dict = {
    "sitemaps": {
        "pages": PagesSitemap(),
        "plans": PlansSitemap(),
        "repos": ReposSitemap(),
    }
}


urlpatterns = [
    path("", include("totem.pages.urls", namespace="pages")),
    path("plans/", include("totem.plans.urls", namespace="plans")),
    path("course/", include("totem.course.urls", namespace="course")),
    path("repos/", include("totem.repos.urls", namespace="repos")),
    path("email/", include("totem.email.urls", namespace="email")),
    path("circles/", include("totem.circles.urls", namespace="circles")),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # API
    path("api/v1/", api.urls),  # type: ignore
    # User management
    path("users/", include("totem.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    path(
        "sitemap.xml",
        sitemap,
        sitemap_dict,
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path("onboard/", include("totem.onboard.urls")),
    path("auth/link/", MagicLoginView.as_view(), name="magic-login"),
    path("dev/", include("totem.dev.urls", namespace="dev"))
    # Your stuff: custom urls includes go here
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if settings.DEBUG:
    # Static file serving when using Gunicorn + Uvicorn for local web socket development
    urlpatterns += staticfiles_urlpatterns()


if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
