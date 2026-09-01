"""
Role-based access control mixins.

Used by every role-scoped view from Phase 1 onward. A user who reaches a view
for a role they do not hold is redirected to their own dashboard with an
explanatory message rather than shown a bare 403 — they are authenticated and
legitimate, just in the wrong place.

Note that ``Role.ADMIN`` (an academic administrator) is independent of
``is_staff`` (Django admin site access). Do not conflate them.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

from .models import Role


class RoleRequiredMixin(LoginRequiredMixin):
    """Restrict a view to one or more roles. Set ``allowed_roles``."""

    allowed_roles: tuple[str, ...] = ()
    wrong_role_message = _("You do not have access to that page.")

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            # Let LoginRequiredMixin handle the redirect to the login page.
            return super().dispatch(request, *args, **kwargs)

        if self.allowed_roles and request.user.role not in self.allowed_roles:
            messages.warning(request, self.wrong_role_message)
            return redirect(request.user.dashboard_url_name)

        return super().dispatch(request, *args, **kwargs)


class StudentRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.STUDENT,)
    wrong_role_message = _("That page is only available to students.")


class LecturerRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.LECTURER,)
    wrong_role_message = _("That page is only available to lecturers.")


class AdministratorRequiredMixin(RoleRequiredMixin):
    allowed_roles = (Role.ADMIN,)
    wrong_role_message = _("That page is only available to administrators.")
