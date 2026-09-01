"""Root URL configuration for CRS."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("catalogue/", include("academics.urls")),
    path("registration/", include("registration.urls")),
    path("api/v1/", include("api.urls")),
    path("", RedirectView.as_view(pattern_name="accounts:dashboard", permanent=False), name="home"),
]

admin.site.site_header = "CRS Administration"
admin.site.site_title = "CRS Admin"
admin.site.index_title = "Course Registration System"
