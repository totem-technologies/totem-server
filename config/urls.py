from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps import views as sitemaps_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import include, path
from django.views import defaults as default_views
from django.views.decorators.cache import cache_page
from django.views.generic import RedirectView

from totem.api.api import api, mobile_api
from totem.blog.urls import BlogSitemap
from totem.pages.urls import PagesSitemap
from totem.plans.urls import PlansSitemap
from totem.repos.urls import ReposSitemap
from totem.spaces.urls import SpacesSitemap
from totem.users import views as user_views
from totem.utils.exports import get_url_patterns as export_url_patterns

sitemaps = {
    "pages": PagesSitemap(),
    "plans": PlansSitemap(),
    "repos": ReposSitemap(),
    "spaces": SpacesSitemap(),
    "blog": BlogSitemap(),
}

try:
    # This raises an error when other errors happen. Reduce noise.
    api_path = path("api/v1/", api.urls)  # type: ignore
    mobile_api_path = path("api/mobile/", mobile_api.urls)  # type: ignore
except Exception:
    api_path = None
    mobile_api_path = None


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
    + export_url_patterns()
    + admin.site.get_urls(),
    "admin",
    admin.site.name,
)


def apple_app_site_association(request):
    data = {
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": f"{settings.IOS_TEAM_ID}.{settings.IOS_BUNDLE_ID}",
                    "paths": ["/spaces/*", "/blog/*", "/keeper/*"],
                }
            ],
        }
    }
    return JsonResponse(data, content_type="application/json")


def asset_links(request):
    data = [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": settings.ANDROID_PACKAGE_NAME,
                "sha256_cert_fingerprints": [settings.ANDROID_CERT_FINGERPRINT],
            },
        }
    ]
    return JsonResponse(data, safe=False, content_type="application/json")


urlpatterns = [
    path(".well-known/apple-app-site-association", apple_app_site_association),
    path(".well-known/assetlinks.json", asset_links),
    path("", include("totem.pages.urls", namespace="pages")),
    path("plans/", include("totem.plans.urls", namespace="plans")),
    path("course/", include("totem.course.urls", namespace="course")),
    path("repos/", include("totem.repos.urls", namespace="repos")),
    path("email/", include("totem.email.urls", namespace="email")),
    path("spaces/", include("totem.spaces.urls", namespace="spaces")),
    path("blog/", include("totem.blog.urls", namespace="blog")),
    # Django Admin, use {% url 'admin:index' %}
    path(f"admin/{settings.ADMIN_URL}", admin_urls),
    # User management
    path("users/", include("totem.users.urls", namespace="users")),

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
    path("dev/", include("totem.dev.urls", namespace="dev")),
    # Redirects
    path("circles/", RedirectView.as_view(url="/spaces/", permanent=True)),
    path("circles/<path:path>", RedirectView.as_view(url="/spaces/%(path)s", permanent=True)),
]
# API
if api_path:
    urlpatterns += [api_path]
if mobile_api_path:
    urlpatterns += [mobile_api_path]

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
