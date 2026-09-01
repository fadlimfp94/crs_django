"""Catalogue browsing and term-window administration forms."""

from django import forms

from .models import Department, Term


class CatalogueFilterForm(forms.Form):
    """
    Every field is optional — an empty submission just means "no filter".

    Bound directly from ``request.GET`` so the filtered view is a shareable,
    bookmarkable URL.
    """

    department = forms.ModelChoiceField(
        queryset=Department.objects.all(), required=False, empty_label="Any department"
    )
    term = forms.ModelChoiceField(
        queryset=Term.objects.all(), required=False, empty_label="Any term"
    )
    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(attrs={"placeholder": "Course code or title"}),
    )
    min_credits = forms.IntegerField(required=False, min_value=1, max_value=12)
    max_credits = forms.IntegerField(required=False, min_value=1, max_value=12)
    availability = forms.ChoiceField(
        required=False,
        choices=[("", "Any"), ("open", "Open seats"), ("waitlist", "Waitlist only")],
    )


class TermWindowForm(forms.ModelForm):
    """
    Registration-window control for administrators.

    Deliberately excludes ``is_active`` — toggling the current term has to go
    through Django admin, where the partial-unique-active-term constraint is
    already handled correctly. This form only ever touches one term's own
    window and ceiling.
    """

    class Meta:
        model = Term
        fields = ["registration_opens_at", "registration_closes_at", "max_credits_per_student"]
        widgets = {
            "registration_opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "registration_closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
