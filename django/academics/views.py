"""
Catalogue browsing (every role) and registration-window administration.

Register/drop/timetable screens live in ``registration.views`` instead —
they operate on ``Enrollment``, not on catalogue data.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, UpdateView

from accounts.mixins import AdministratorRequiredMixin
from registration.models import Enrollment
from registration.services import seats_remaining

from .forms import CatalogueFilterForm, TermWindowForm
from .models import Section, Term


class CatalogueListView(LoginRequiredMixin, ListView):
    """Every authenticated role may browse the catalogue."""

    template_name = "academics/catalogue.html"
    context_object_name = "sections"
    paginate_by = 20

    def get_queryset(self):
        request_get = self.request.GET
        self.filter_form = CatalogueFilterForm(request_get)
        self.filter_form.is_valid()
        cleaned = self.filter_form.cleaned_data

        queryset = Section.objects.select_related(
            "course", "term", "lecturer__user"
        ).prefetch_related("meetings")

        department = cleaned.get("department")
        if department:
            queryset = queryset.filter(course__department=department)

        term = cleaned.get("term")
        if term is None and "term" not in request_get:
            # First visit, no filters submitted yet: default to the current term.
            term = Term.objects.filter(is_active=True).first()
        if term:
            queryset = queryset.filter(term=term)

        query = cleaned.get("q")
        if query:
            queryset = queryset.filter(
                Q(course__code__icontains=query) | Q(course__title__icontains=query)
            )

        min_credits = cleaned.get("min_credits")
        if min_credits is not None:
            queryset = queryset.filter(course__credits__gte=min_credits)

        max_credits = cleaned.get("max_credits")
        if max_credits is not None:
            queryset = queryset.filter(course__credits__lte=max_credits)

        # Seat counts are not stored, so availability filtering happens in
        # Python once the rest of the query has narrowed things down.
        sections = list(queryset)
        for section in sections:
            section.seats_remaining = seats_remaining(section)

        availability = cleaned.get("availability")
        if availability == "open":
            sections = [s for s in sections if s.seats_remaining > 0]
        elif availability == "waitlist":
            sections = [s for s in sections if s.seats_remaining == 0]

        return sections

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = self.filter_form
        params = self.request.GET.copy()
        params.pop("page", None)
        context["querystring"] = params.urlencode()
        return context


class SectionDetailView(LoginRequiredMixin, DetailView):
    queryset = Section.objects.select_related("course", "term", "lecturer__user").prefetch_related(
        "meetings"
    )
    template_name = "academics/section_detail.html"
    context_object_name = "section"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        section = self.object
        context["seats_remaining"] = seats_remaining(section)
        user = self.request.user
        if user.is_student:
            context["enrollment"] = Enrollment.objects.filter(
                student=user.student_profile, section=section
            ).first()
        return context


class TermWindowListView(AdministratorRequiredMixin, ListView):
    queryset = Term.objects.all()
    template_name = "academics/term_window_list.html"
    context_object_name = "terms"


class TermWindowUpdateView(AdministratorRequiredMixin, UpdateView):
    model = Term
    form_class = TermWindowForm
    template_name = "academics/term_window_form.html"
    success_url = reverse_lazy("academics:admin_term_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Updated the registration window for {self.object}.")
        return response
