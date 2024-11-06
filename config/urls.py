from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps import views as sitemaps_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.shortcuts import redirect
from django.urls import include, path
from django.views import defaults as default_views
from django.views.decorators.cache import cache_page
from django.views.generic import RedirectView

from totem.api.api import api
from totem.circles.urls import SpacesSitemap
from totem.pages.urls import PagesSitemap
from totem.plans.urls import PlansSitemap
from totem.repos.urls import ReposSitemap
from totem.users import views as user_views
from totem.users.views import MagicLoginView

sitemaps = {
    "pages": PagesSitemap(),
    "plans": PlansSitemap(),
    "repos": ReposSitemap(),
    "spaces": SpacesSitemap(),
}

try:
    # This raises an error when other errors happen. Reduce noise.
    api_path = path("api/v1/", api.urls)  # type: ignore
except Exception:
    api_path = None


_reserved_paths = [
    "admin",
    "api",
    "auth",
    "blog",
    "careers",
    "docs",
    "legal",
    "local",
    "media",
    "members",
    "status",
    "support",
]


def reservedView(request):
    return redirect("pages:home")


admin_urls = (
    # Use default login view for admin
    [path("login/", RedirectView.as_view(pattern_name=settings.LOGIN_URL, permanent=True, query_string=True))]
    + admin.site.get_urls(),
    "admin",
    admin.site.name,
)

urlpatterns = [
    path("", include("totem.pages.urls", namespace="pages")),
    path("plans/", include("totem.plans.urls", namespace="plans")),
    path("course/", include("totem.course.urls", namespace="course")),
    path("repos/", include("totem.repos.urls", namespace="repos")),
    path("email/", include("totem.email.urls", namespace="email")),
    path("circles/", include("totem.circles.urls", namespace="circles")),
    # Django Admin, use {% url 'admin:index' %}
    path(f"admin/{settings.ADMIN_URL}", admin_urls),  # type: ignore
    # API
    api_path,
    # User management
    path("users/", include("totem.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    path("_impersonate/", include("impersonate.urls")),
    path(
        "sitemap.xml",
        cache_page(86400)(sitemaps_views.index),
        {"sitemaps": sitemaps, "sitemap_url_name": "sitemaps"},
        name="sitemaps_index",
    ),
    path(
        "sitemap-<section>.xml",
        cache_page(86400)(sitemaps_views.sitemap),
        {"sitemaps": sitemaps},
        name="sitemaps",
    ),
    path("onboard/", include("totem.onboard.urls")),
    path("auth/link/", MagicLoginView.as_view(), name="magic-login"),
    path("dev/", include("totem.dev.urls", namespace="dev")),
]

if not settings.USE_S3_STORAGE:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

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

# save some paths for later
urlpatterns += [path(f"{p}/", reservedView) for p in _reserved_paths]

# must be last
urlpatterns += [path("<str:name>/", user_views.profiles, name="profiles")]  # type: ignore
