"""
Role-based permission classes for the API — the DRF-shaped counterpart to
``accounts.mixins.RoleRequiredMixin``. Both delegate to the same
``is_student``/``is_lecturer``/``is_administrator`` properties on ``User``, so
a role check is never duplicated between the web UI and the API.
"""

from rest_framework.permissions import BasePermission


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_student


class IsLecturer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_lecturer


class IsAdministrator(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_administrator
