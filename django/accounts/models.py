"""
Identity and profile models for CRS.

One ``User`` row per person, carrying a ``role`` that selects which profile
applies. Role-specific data lives in ``StudentProfile`` / ``LecturerProfile``
rather than on the user, so the user table stays about identity.

``AUTH_USER_MODEL`` is settings-locked to ``accounts.User``. Changing this
model's identity later means destroying the database, so it lands before the
first ``migrate`` (PLAN.md Phase 1).
"""

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    STUDENT = "STUDENT", _("Student")
    LECTURER = "LECTURER", _("Lecturer")
    ADMIN = "ADMIN", _("Administrator")


class StudentStatus(models.TextChoices):
    """
    Academic standing. Only ACTIVE students may register — this backs
    registration rule R7 (PLAN.md §5).
    """

    ACTIVE = "ACTIVE", _("Active")
    PROBATION = "PROBATION", _("Academic probation")
    SUSPENDED = "SUSPENDED", _("Suspended")
    GRADUATED = "GRADUATED", _("Graduated")
    WITHDRAWN = "WITHDRAWN", _("Withdrawn")


class LecturerTitle(models.TextChoices):
    PROFESSOR = "PROF", _("Professor")
    ASSOCIATE_PROFESSOR = "ASSOC_PROF", _("Associate Professor")
    ASSISTANT_PROFESSOR = "ASST_PROF", _("Assistant Professor")
    LECTURER = "LECTURER", _("Lecturer")
    INSTRUCTOR = "INSTRUCTOR", _("Instructor")


identifier_validator = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9\-]*$",
    message=_("Use letters, digits and hyphens only, starting with a letter or digit."),
)


class UserManager(DjangoUserManager):
    """
    Adds role-aware creation helpers.

    ``create_student`` / ``create_lecturer`` create the user and its profile in
    one transaction, so a role can never exist without the profile it implies.
    Seed commands and tests go through these.
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)

    @transaction.atomic
    def create_student(self, username, email, password=None, *, student_number=None, **extra):
        """Create a STUDENT user together with its StudentProfile."""
        profile_fields = {
            key: extra.pop(key) for key in ("enrollment_year", "status") if key in extra
        }
        extra["role"] = Role.STUDENT
        user = self.create_user(username, email, password, **extra)
        StudentProfile.objects.create(
            user=user,
            student_number=student_number or username,
            **profile_fields,
        )
        return user

    @transaction.atomic
    def create_lecturer(self, username, email, password=None, *, staff_number=None, **extra):
        """Create a LECTURER user together with its LecturerProfile."""
        profile_fields = {key: extra.pop(key) for key in ("title",) if key in extra}
        extra["role"] = Role.LECTURER
        user = self.create_user(username, email, password, **extra)
        LecturerProfile.objects.create(
            user=user,
            staff_number=staff_number or username,
            **profile_fields,
        )
        return user


class User(AbstractUser):
    """
    A CRS account.

    Login uses ``username``, which by convention is the person's student or
    staff number. ``email`` is required and unique — it is the recovery
    channel and the natural cross-system key.
    """

    email = models.EmailField(_("email address"), unique=True)
    role = models.CharField(
        _("role"),
        max_length=10,
        choices=Role.choices,
        db_index=True,
        help_text=_("Determines which dashboard and permissions apply."),
    )

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            # choices alone is form-level validation; this enforces it in the database.
            models.CheckConstraint(
                condition=models.Q(role__in=[r.value for r in Role]),
                name="accounts_user_role_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.username})"

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    @property
    def is_student(self) -> bool:
        return self.role == Role.STUDENT

    @property
    def is_lecturer(self) -> bool:
        return self.role == Role.LECTURER

    @property
    def is_administrator(self) -> bool:
        """Role-based admin. Deliberately distinct from ``is_staff``/``is_superuser``."""
        return self.role == Role.ADMIN

    @property
    def dashboard_url_name(self) -> str:
        """Named URL of the dashboard this user lands on after login."""
        return {
            Role.STUDENT: "accounts:student_dashboard",
            Role.LECTURER: "accounts:lecturer_dashboard",
            Role.ADMIN: "accounts:admin_dashboard",
        }.get(self.role, "accounts:profile")


class StudentProfile(models.Model):
    """Academic record for a STUDENT user."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        primary_key=True,
    )
    student_number = models.CharField(
        _("student number"),
        max_length=20,
        unique=True,
        validators=[identifier_validator],
    )
    enrollment_year = models.PositiveIntegerField(
        _("enrollment year"),
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
        default=2026,
    )
    status = models.CharField(
        _("academic standing"),
        max_length=10,
        choices=StudentStatus.choices,
        default=StudentStatus.ACTIVE,
        db_index=True,
    )
    # Phase 2 adds:  program = FK(academics.Program)

    class Meta:
        verbose_name = _("student profile")
        verbose_name_plural = _("student profiles")
        ordering = ["student_number"]

    def __str__(self) -> str:
        return f"{self.student_number} — {self.user.display_name}"

    @property
    def may_register(self) -> bool:
        """Rule R7: only students in good standing may register."""
        return self.status == StudentStatus.ACTIVE


class LecturerProfile(models.Model):
    """Employment record for a LECTURER user."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="lecturer_profile",
        primary_key=True,
    )
    staff_number = models.CharField(
        _("staff number"),
        max_length=20,
        unique=True,
        validators=[identifier_validator],
    )
    title = models.CharField(
        _("title"),
        max_length=10,
        choices=LecturerTitle.choices,
        default=LecturerTitle.LECTURER,
    )
    # Phase 2 adds:  department = FK(academics.Department)

    class Meta:
        verbose_name = _("lecturer profile")
        verbose_name_plural = _("lecturer profiles")
        ordering = ["staff_number"]

    def __str__(self) -> str:
        return f"{self.get_title_display()} {self.user.display_name}"
