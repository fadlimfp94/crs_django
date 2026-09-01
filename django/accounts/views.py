"""
Authentication and dashboard views.

The dashboards are intentionally placeholders in Phase 1 — they establish
routing, role separation, and navigation so later phases have somewhere to
attach real content.
"""

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView, View

from registration.models import EnrollmentStatus

from .forms import CRSAuthenticationForm
from .mixins import AdministratorRequiredMixin, LecturerRequiredMixin, StudentRequiredMixin


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    form_class = CRSAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        # Honour ?next= when present, otherwise send the user to their own dashboard.
        return self.get_redirect_url() or reverse_lazy(self.request.user.dashboard_url_name)


class LogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.method == "POST":
            messages.success(request, _("You have been signed out."))
        return super().dispatch(request, *args, **kwargs)


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:password_change_done")


class PasswordChangeDoneView(auth_views.PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"


class DashboardRedirectView(LoginRequiredMixin, View):
    """
    Single entry point after login.

    Keeping one ``accounts:dashboard`` target means ``LOGIN_REDIRECT_URL`` and
    every "home" link work for all roles without branching at the call site.
    """

    def get(self, request, *args, **kwargs):
        return redirect(request.user.dashboard_url_name)


class StudentDashboardView(StudentRequiredMixin, TemplateView):
    template_name = "accounts/student_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["enrolled_count"] = self.request.user.student_profile.enrollments.filter(
            status=EnrollmentStatus.ENROLLED
        ).count()
        return context


class LecturerDashboardView(LecturerRequiredMixin, TemplateView):
    template_name = "accounts/lecturer_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["section_count"] = self.request.user.lecturer_profile.sections.count()
        return context


class AdministratorDashboardView(AdministratorRequiredMixin, TemplateView):
    template_name = "accounts/admin_dashboard.html"


class ProfileView(LoginRequiredMixin, TemplateView):
    """Read-only account details. Editing arrives with the fuller UI in Phase 4."""

    template_name = "accounts/profile.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["profile"] = getattr(
            user, "student_profile", getattr(user, "lecturer_profile", None)
        )
        return context
