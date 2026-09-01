from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academics"
    verbose_name = _("Academic catalogue")
