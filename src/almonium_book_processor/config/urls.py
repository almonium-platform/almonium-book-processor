from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from almonium_book_processor.catalog.views import health

urlpatterns = [
    path("", include("almonium_book_processor.catalog.urls")),
    path("admin/", admin.site.urls),
    path("api/v1/", include("almonium_book_processor.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    path("healthz/", health, name="health"),
]
