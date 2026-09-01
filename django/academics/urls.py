"""URL patterns for catalogue browsing and term-window administration."""

from django.urls import path

from . import views

app_name = "academics"

urlpatterns = [
    path("", views.CatalogueListView.as_view(), name="catalogue"),
    path("sections/<int:pk>/", views.SectionDetailView.as_view(), name="section_detail"),
    path("admin/terms/", views.TermWindowListView.as_view(), name="admin_term_list"),
    path("admin/terms/<int:pk>/", views.TermWindowUpdateView.as_view(), name="admin_term_update"),
]
