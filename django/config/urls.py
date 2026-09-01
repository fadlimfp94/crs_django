"""Root URL configuration for CRS."""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    # Phase 2:   path("catalogue/", include("academics.urls")),
    # Phase 3-4: path("registration/", include("registration.urls")),
    # Phase 5:   path("api/v1/", include("api.urls")),
    path("", RedirectView.as_view(pattern_name="accounts:dashboard", permanent=False), name="home"),
]

admin.site.site_header = "CRS Administration"
admin.site.site_title = "CRS Admin"
admin.site.index_title = "Course Registration System"
