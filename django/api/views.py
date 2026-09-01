"""
DRF viewsets — a second front door onto the same models and, for
register/drop/grade/override, the same ``registration.services`` functions
the Phase 4 templates already call. No business rule is re-implemented here.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.decorators import action
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from academics.models import Course, Section, Term
from registration import services
from registration.models import Enrollment, EnrollmentStatus

from .permissions import IsAdministrator, IsLecturer, IsStudent
from .serializers import (
    CourseSerializer,
    EnrollmentSerializer,
    GradeInputSerializer,
    MeSerializer,
    OverrideInputSerializer,
    RosterEnrollmentSerializer,
    SectionSerializer,
    TermSerializer,
    TermWindowUpdateSerializer,
)


def _parse_bool(value: str) -> bool:
    return value.lower() in ("1", "true", "yes")


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer

    def get_queryset(self):
        queryset = Course.objects.select_related("department").prefetch_related(
            "prerequisite_rules__prerequisite"
        )
        params = self.request.query_params

        department = params.get("department")
        if department:
            queryset = queryset.filter(department__code=department)

        query = params.get("q")
        if query:
            queryset = queryset.filter(Q(code__icontains=query) | Q(title__icontains=query))

        level = params.get("level")
        if level:
            queryset = queryset.filter(level=level)

        is_active = params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=_parse_bool(is_active))

        return queryset


class SectionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SectionSerializer

    def get_queryset(self):
        base = Section.objects.select_related(
            "course__department", "term", "lecturer__user"
        ).prefetch_related("meetings", "course__prerequisite_rules__prerequisite")

        # Roster is scoped to the requesting lecturer's own sections only, so
        # a mismatched lecturer 404s via get_object() rather than exposing
        # another lecturer's roster.
        if self.action == "roster":
            return base.filter(lecturer=self.request.user.lecturer_profile)

        queryset = base
        params = self.request.query_params

        department = params.get("department")
        if department:
            queryset = queryset.filter(course__department__code=department)

        term_code = params.get("term")
        if term_code:
            queryset = queryset.filter(term__code=term_code)
        elif self.action == "list" and "term" not in params:
            active_term = Term.objects.filter(is_active=True).first()
            if active_term:
                queryset = queryset.filter(term=active_term)

        query = params.get("q")
        if query:
            queryset = queryset.filter(
                Q(course__code__icontains=query) | Q(course__title__icontains=query)
            )

        min_credits = params.get("min_credits")
        if min_credits:
            queryset = queryset.filter(course__credits__gte=min_credits)

        max_credits = params.get("max_credits")
        if max_credits:
            queryset = queryset.filter(course__credits__lte=max_credits)

        if params.get("mine") == "true" and self.request.user.is_lecturer:
            queryset = queryset.filter(lecturer=self.request.user.lecturer_profile)

        if self.action != "list":
            # retrieve/register need a real QuerySet so get_object() keeps
            # working — only `list` materializes to a Python list below.
            return queryset

        sections = list(queryset)
        availability = params.get("availability")
        if availability == "open":
            sections = [s for s in sections if services.seats_remaining(s) > 0]
        elif availability == "waitlist":
            sections = [s for s in sections if services.seats_remaining(s) == 0]
        return sections

    @action(detail=True, methods=["post"], permission_classes=[IsStudent])
    def register(self, request, pk=None):
        section = self.get_object()
        enrollment = services.register(request.user.student_profile, section)
        return Response(EnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], permission_classes=[IsLecturer])
    def roster(self, request, pk=None):
        section = self.get_object()
        enrolled = Enrollment.objects.filter(
            section=section, status=EnrollmentStatus.ENROLLED
        ).select_related("student__user")
        waitlisted = (
            Enrollment.objects.filter(section=section, status=EnrollmentStatus.WAITLISTED)
            .select_related("student__user")
            .order_by("waitlist_position")
        )
        return Response(
            {
                "enrolled": RosterEnrollmentSerializer(enrolled, many=True).data,
                "waitlisted": RosterEnrollmentSerializer(waitlisted, many=True).data,
            }
        )


class TermViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    List/retrieve are open to every authenticated role, unlike Phase 4's
    admin-only term screens — a student needs the registration window (e.g.
    to understand an R1 rejection) and ``SectionSerializer`` already nests it
    for every listed section anyway. Only the write (registration-window
    update) stays admin-only.
    """

    queryset = Term.objects.all()
    serializer_class = TermSerializer

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return TermWindowUpdateSerializer
        return TermSerializer

    def get_permissions(self):
        if self.action in ("update", "partial_update"):
            return [IsAdministrator()]
        return super().get_permissions()


class EnrollmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EnrollmentSerializer

    def get_queryset(self):
        user = self.request.user
        base = Enrollment.objects.select_related(
            "section__course__department", "section__term", "section__lecturer__user"
        )
        if self.action == "grade":
            return base.filter(section__lecturer=user.lecturer_profile)
        if user.is_student:
            return base.filter(student=user.student_profile)
        if user.is_administrator:
            return base
        return Enrollment.objects.none()

    @action(detail=True, methods=["post"], permission_classes=[IsStudent])
    def drop(self, request, pk=None):
        enrollment = get_object_or_404(Enrollment, pk=pk, student=request.user.student_profile)
        enrollment = services.drop(enrollment.student, enrollment.section)
        return Response(EnrollmentSerializer(enrollment).data)

    @action(detail=True, methods=["post"], permission_classes=[IsLecturer])
    def grade(self, request, pk=None):
        enrollment = self.get_object()
        serializer = GradeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enrollment = services.record_grade(enrollment, serializer.validated_data["grade"])
        return Response(EnrollmentSerializer(enrollment).data)

    @action(detail=False, methods=["post"], permission_classes=[IsAdministrator])
    def override(self, request):
        serializer = OverrideInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enrollment = services.override_enrollment(
            serializer.validated_data["student"], serializer.validated_data["section"]
        )
        return Response(EnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)


class MeView(RetrieveAPIView):
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user


class ObtainAuthTokenThrottled(ObtainAuthToken):
    """Adds a per-scope throttle to the stock token-obtain view, and returns
    enough identity to route a client to the right dashboard without a second
    ``/me/`` round trip."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        user = Token.objects.get(key=response.data["token"]).user
        response.data["role"] = user.role
        response.data["display_name"] = user.display_name
        return response
