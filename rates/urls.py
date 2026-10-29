from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import api, views

router = DefaultRouter()
router.register("currencies", api.CurrencyViewSet, basename="currency")

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("currencies/", views.currency_list, name="currency_list"),
    path("currencies/<str:code>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("convert/", views.converter, name="converter"),
    path("api/convert/", api.convert_view, name="api_convert"),
    path("api/", include(router.urls)),
]
