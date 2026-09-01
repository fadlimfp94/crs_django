"""URL patterns for registration, timetable, rosters, and admin override."""

from django.urls import path

from . import views

app_name = "registration"

urlpatterns = [
    path("sections/<int:section_id>/register/", views.RegisterView.as_view(), name="register"),
    path("enrollments/<int:pk>/drop/", views.DropView.as_view(), name="drop"),
    path("my-timetable/", views.MyTimetableView.as_view(), name="my_timetable"),
    path("my-enrollments/", views.EnrollmentHistoryView.as_view(), name="enrollment_history"),
    path("my-sections/", views.LecturerSectionListView.as_view(), name="lecturer_sections"),
    path("sections/<int:pk>/roster/", views.SectionRosterView.as_view(), name="roster"),
    path("enrollments/<int:pk>/grade/", views.GradeEntryView.as_view(), name="grade_entry"),
    path("admin/override/", views.EnrollmentOverrideView.as_view(), name="admin_override"),
]
