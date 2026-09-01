"""URL patterns for authentication and dashboards."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("password/change/", views.PasswordChangeView.as_view(), name="password_change"),
    path(
        "password/change/done/",
        views.PasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    # Dashboards
    path("", views.DashboardRedirectView.as_view(), name="dashboard"),
    path("student/", views.StudentDashboardView.as_view(), name="student_dashboard"),
    path("lecturer/", views.LecturerDashboardView.as_view(), name="lecturer_dashboard"),
    path("administrator/", views.AdministratorDashboardView.as_view(), name="admin_dashboard"),
    path("profile/", views.ProfileView.as_view(), name="profile"),
]
