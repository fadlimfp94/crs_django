"""
Registration screens: register/drop, my timetable, enrollment history,
lecturer roster and grading, administrative override.

Every rule rejection is caught here as ``RegistrationError`` and surfaced
verbatim — never a generic failure message.
"""

from types import SimpleNamespace

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import DetailView, ListView, TemplateView, View

from academics.models import DayOfWeek, Section, Term
from accounts.mixins import AdministratorRequiredMixin, LecturerRequiredMixin, StudentRequiredMixin

from .forms import GradeEntryForm, OverrideEnrollmentForm
from .models import ACTIVE_STATUSES, Enrollment, EnrollmentStatus
from .services import RegistrationError, drop, override_enrollment, record_grade, register


class RegisterView(StudentRequiredMixin, View):
    def get(self, request, section_id):
        section = get_object_or_404(Section.objects.select_related("course", "term"), pk=section_id)
        existing = self._active_enrollment(request, section)
        if existing is not None:
            messages.info(
                request, f"You are already {existing.get_status_display().lower()} for {section}."
            )
            return redirect("academics:section_detail", pk=section.pk)
        return render(request, "registration/register_confirm.html", {"section": section})

    def post(self, request, section_id):
        section = get_object_or_404(Section, pk=section_id)
        try:
            enrollment = register(request.user.student_profile, section)
        except RegistrationError as exc:
            return render(
                request,
                "registration/register_confirm.html",
                {"section": section, "error": exc},
            )
        if enrollment.status == EnrollmentStatus.WAITLISTED:
            messages.warning(
                request,
                f"{section} is full. You are #{enrollment.waitlist_position} on the waitlist.",
            )
        else:
            messages.success(request, f"You are registered for {section}.")
        return redirect("academics:section_detail", pk=section.pk)

    @staticmethod
    def _active_enrollment(request, section):
        return Enrollment.objects.filter(
            student=request.user.student_profile, section=section, status__in=ACTIVE_STATUSES
        ).first()


class DropView(StudentRequiredMixin, View):
    def get(self, request, pk):
        enrollment = get_object_or_404(
            Enrollment.objects.select_related("section__course"),
            pk=pk,
            student=request.user.student_profile,
        )
        return render(request, "registration/drop_confirm.html", {"enrollment": enrollment})

    def post(self, request, pk):
        enrollment = get_object_or_404(Enrollment, pk=pk, student=request.user.student_profile)
        try:
            drop(enrollment.student, enrollment.section)
            messages.success(request, f"Dropped {enrollment.section}.")
        except RegistrationError as exc:
            messages.error(request, str(exc))
        return redirect("registration:enrollment_history")


def _time_to_tick(t) -> int:
    """Half-hour ticks since midnight, floored."""
    return (t.hour * 60 + t.minute) // 30


def _ceil_time_to_tick(t) -> int:
    """Half-hour ticks since midnight, ceiled — so a meeting's own span always covers it."""
    minutes = t.hour * 60 + t.minute
    return -(-minutes // 30)


def _tick_to_label(tick: int) -> str:
    minutes = tick * 30
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class MyTimetableView(StudentRequiredMixin, TemplateView):
    template_name = "registration/my_timetable.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        term = Term.objects.filter(is_active=True).first()

        enrollments = []
        if term is not None:
            enrollments = (
                Enrollment.objects.filter(
                    student=self.request.user.student_profile,
                    status=EnrollmentStatus.ENROLLED,
                    section__term=term,
                )
                .select_related("section__course")
                .prefetch_related("section__meetings")
            )

        pairs = [
            (enrollment, meeting)
            for enrollment in enrollments
            for meeting in enrollment.section.meetings.all()
        ]

        blocks = []
        hour_ticks = []
        total_rows = 0
        if pairs:
            # Row 1 is reserved for the day-of-week header, so every tick is
            # offset by one extra row below it.
            start_tick = min(_time_to_tick(meeting.start_time) for _, meeting in pairs)
            end_tick = max(_ceil_time_to_tick(meeting.end_time) for _, meeting in pairs)
            total_rows = end_tick - start_tick + 1
            for enrollment, meeting in pairs:
                blocks.append(
                    SimpleNamespace(
                        course=enrollment.section.course,
                        section=enrollment.section,
                        meeting=meeting,
                        grid_row=_time_to_tick(meeting.start_time) - start_tick + 2,
                        grid_row_span=(
                            _ceil_time_to_tick(meeting.end_time) - _time_to_tick(meeting.start_time)
                        ),
                        grid_column=meeting.day_of_week + 2,
                    )
                )
            hour_ticks = [
                SimpleNamespace(row=tick - start_tick + 2, label=_tick_to_label(tick))
                for tick in range(start_tick, end_tick, 2)
            ]

        context.update(
            {
                "term": term,
                "blocks": blocks,
                "hour_ticks": hour_ticks,
                "total_rows": total_rows,
                "days": DayOfWeek.choices,
            }
        )
        return context


class EnrollmentHistoryView(StudentRequiredMixin, ListView):
    template_name = "registration/enrollment_history.html"
    context_object_name = "enrollments"

    def get_queryset(self):
        return Enrollment.objects.filter(student=self.request.user.student_profile).select_related(
            "section__course", "section__term"
        )


class LecturerSectionListView(LecturerRequiredMixin, ListView):
    template_name = "registration/lecturer_sections.html"
    context_object_name = "sections"

    def get_queryset(self):
        return Section.objects.filter(lecturer=self.request.user.lecturer_profile).select_related(
            "course", "term"
        )


class SectionRosterView(LecturerRequiredMixin, DetailView):
    template_name = "registration/roster.html"
    context_object_name = "section"

    def get_queryset(self):
        return Section.objects.filter(lecturer=self.request.user.lecturer_profile).select_related(
            "course", "term"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        section = self.object
        enrolled = Enrollment.objects.filter(
            section=section, status=EnrollmentStatus.ENROLLED
        ).select_related("student__user")
        context["enrolled"] = [(enrollment, GradeEntryForm()) for enrollment in enrolled]
        context["waitlisted"] = (
            Enrollment.objects.filter(section=section, status=EnrollmentStatus.WAITLISTED)
            .select_related("student__user")
            .order_by("waitlist_position")
        )
        return context


class GradeEntryView(LecturerRequiredMixin, View):
    def post(self, request, pk):
        enrollment = get_object_or_404(
            Enrollment.objects.filter(section__lecturer=request.user.lecturer_profile), pk=pk
        )
        form = GradeEntryForm(request.POST)
        if form.is_valid():
            try:
                record_grade(enrollment, form.cleaned_data["grade"])
                messages.success(request, f"Recorded a grade for {enrollment.student}.")
            except RegistrationError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "Choose a valid grade.")
        return redirect("registration:roster", pk=enrollment.section_id)


class EnrollmentOverrideView(AdministratorRequiredMixin, View):
    def get(self, request):
        return render(
            request, "registration/admin_override.html", {"form": OverrideEnrollmentForm()}
        )

    def post(self, request):
        form = OverrideEnrollmentForm(request.POST)
        if form.is_valid():
            enrollment = override_enrollment(
                form.cleaned_data["student"], form.cleaned_data["section"]
            )
            messages.success(
                request,
                f"{enrollment.student} is now {enrollment.get_status_display().lower()} "
                f"in {enrollment.section}.",
            )
            form = OverrideEnrollmentForm()
        return render(request, "registration/admin_override.html", {"form": form})
