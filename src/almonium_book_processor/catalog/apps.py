from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "almonium_book_processor.catalog"
    verbose_name = "Book processing"
