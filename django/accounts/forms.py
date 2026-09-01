"""Authentication and admin forms for the accounts app."""

from django.contrib.auth.forms import AuthenticationForm, UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import User


class CRSAuthenticationForm(AuthenticationForm):
    """
    Login form.

    Adds autofocus and autocomplete hints, and relabels the username field —
    students know the value as their student number, not a "username".
    """

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _(
            "No account matches that student/staff number and password. "
            "Check for typos and remember that the password is case-sensitive."
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Student / staff number")
        self.fields["username"].widget.attrs.update(
            {
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": _("e.g. 2026001"),
                "data-testid": "login-username",
            }
        )
        self.fields["password"].widget.attrs.update(
            {"autocomplete": "current-password", "data-testid": "login-password"}
        )


class CRSUserCreationForm(UserCreationForm):
    """Admin-site user creation, extended with the required role field."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "role")


class CRSUserChangeForm(UserChangeForm):
    """Admin-site user editing."""

    class Meta(UserChangeForm.Meta):
        model = User
