"""
Serializers for the REST API.

These describe the same data Phase 4's templates already render — no new
business logic lives here. The one exception is ``TermWindowUpdateSerializer``,
which duplicates the window-ordering check ``TermWindowForm`` gets for free
from ``Model.full_clean()`` (a plain ``ModelSerializer.is_valid()`` does not
call that); see its docstring.
"""

from rest_framework import serializers

from academics.grades import Grade
from academics.models import Course, Department, Meeting, PrerequisiteRule, Section, Term
from accounts.models import StudentProfile
from registration.models import Enrollment
from registration.services import seats_remaining


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "code", "name"]


class PrerequisiteRuleSerializer(serializers.ModelSerializer):
    prerequisite_code = serializers.CharField(source="prerequisite.code", read_only=True)
    prerequisite_title = serializers.CharField(source="prerequisite.title", read_only=True)

    class Meta:
        model = PrerequisiteRule
        fields = ["prerequisite_code", "prerequisite_title", "minimum_grade"]


class CourseSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    prerequisite_rules = PrerequisiteRuleSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "code",
            "title",
            "description",
            "credits",
            "department",
            "level",
            "is_active",
            "prerequisite_rules",
        ]


class MeetingSerializer(serializers.ModelSerializer):
    day_of_week_display = serializers.CharField(source="get_day_of_week_display", read_only=True)

    class Meta:
        model = Meeting
        fields = ["day_of_week", "day_of_week_display", "start_time", "end_time", "room"]


class TermSerializer(serializers.ModelSerializer):
    registration_status = serializers.CharField(read_only=True)

    class Meta:
        model = Term
        fields = [
            "id",
            "code",
            "name",
            "start_date",
            "end_date",
            "registration_opens_at",
            "registration_closes_at",
            "is_active",
            "max_credits_per_student",
            "registration_status",
        ]


class TermWindowUpdateSerializer(TermSerializer):
    """
    The API counterpart of ``academics.forms.TermWindowForm`` — same three
    writable fields, same deliberate exclusion of ``is_active``.

    ``ModelForm._post_clean()`` calls ``instance.full_clean()``, which (Django
    4.1+) runs ``validate_constraints()`` and so catches an inverted window via
    the ``academics_term_registration_window_ordered`` DB constraint for free.
    A plain ``ModelSerializer.is_valid()`` does not call ``full_clean()``, so
    the same check is reproduced explicitly here — against ``self.instance``'s
    current values, not just ``attrs``, so a `PATCH` that only supplies one
    side of the pair is still checked against the other side's stored value.
    """

    class Meta(TermSerializer.Meta):
        fields = ["registration_opens_at", "registration_closes_at", "max_credits_per_student"]

    def validate(self, attrs):
        opens = attrs.get("registration_opens_at", self.instance.registration_opens_at)
        closes = attrs.get("registration_closes_at", self.instance.registration_closes_at)
        if closes <= opens:
            raise serializers.ValidationError("Registration must close after it opens.")
        return attrs


class SectionSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    term = TermSerializer(read_only=True)
    lecturer_name = serializers.CharField(read_only=True)
    seats_remaining = serializers.SerializerMethodField()
    meetings = MeetingSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = [
            "id",
            "course",
            "term",
            "section_code",
            "lecturer_name",
            "capacity",
            "seats_remaining",
            "meetings",
        ]

    def get_seats_remaining(self, section) -> int:
        return seats_remaining(section)


class EnrollmentSerializer(serializers.ModelSerializer):
    section = SectionSerializer(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "section",
            "status",
            "status_display",
            "waitlist_position",
            "grade",
            "registered_at",
            "dropped_at",
        ]


class RosterEnrollmentSerializer(EnrollmentSerializer):
    student = serializers.SerializerMethodField()

    class Meta(EnrollmentSerializer.Meta):
        fields = [*EnrollmentSerializer.Meta.fields, "student"]

    def get_student(self, enrollment):
        return {
            "student_number": enrollment.student.student_number,
            "display_name": enrollment.student.user.display_name,
        }


class GradeInputSerializer(serializers.Serializer):
    grade = serializers.ChoiceField(choices=Grade.choices)


class OverrideInputSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=StudentProfile.objects.all())
    section = serializers.PrimaryKeyRelatedField(queryset=Section.objects.all())


class MeSerializer(serializers.Serializer):
    """
    Not backed by a model — ``request.user`` plus whichever profile its role
    implies. ``StudentProfile``/``LecturerProfile`` use ``user`` as their
    primary key, so there is no separate profile id to expose.
    """

    def to_representation(self, user):
        data = {
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        }
        if user.is_student:
            profile = user.student_profile
            data["student"] = {
                "student_number": profile.student_number,
                "status": profile.status,
                "enrollment_year": profile.enrollment_year,
                "program": profile.program.code if profile.program else None,
                "may_register": profile.may_register,
            }
        elif user.is_lecturer:
            profile = user.lecturer_profile
            data["lecturer"] = {
                "staff_number": profile.staff_number,
                "title": profile.title,
                "department": profile.department.code if profile.department else None,
            }
        return data
