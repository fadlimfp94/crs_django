"""URL configuration for the REST API — mounted at ``/api/v1/`` in config/urls.py."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from .views import (
    CourseViewSet,
    EnrollmentViewSet,
    MeView,
    ObtainAuthTokenThrottled,
    SectionViewSet,
    TermViewSet,
)

app_name = "api"

router = DefaultRouter()
router.register("courses", CourseViewSet, basename="course")
router.register("sections", SectionViewSet, basename="section")
router.register("terms", TermViewSet, basename="term")
router.register("enrollments", EnrollmentViewSet, basename="enrollment")

urlpatterns = [
    path("auth/token/", ObtainAuthTokenThrottled.as_view(), name="token-obtain"),
    path("me/", MeView.as_view(), name="me"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
    path("", include(router.urls)),
]
