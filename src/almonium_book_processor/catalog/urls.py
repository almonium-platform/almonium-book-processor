from django.urls import path

from almonium_book_processor.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("upload/", views.upload_source, name="upload"),
    path("imports/legacy/", views.import_legacy, name="import-legacy"),
    path("editions/<uuid:edition_id>/", views.edition_detail, name="edition-detail"),
]
