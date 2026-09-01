"""Forms for grade entry and administrative enrollment override."""

from django import forms

from academics.grades import Grade
from academics.models import Section
from accounts.models import StudentProfile


class GradeEntryForm(forms.Form):
    grade = forms.ChoiceField(choices=Grade.choices)


class OverrideEnrollmentForm(forms.Form):
    student = forms.ModelChoiceField(queryset=StudentProfile.objects.select_related("user"))
    section = forms.ModelChoiceField(queryset=Section.objects.select_related("course", "term"))
