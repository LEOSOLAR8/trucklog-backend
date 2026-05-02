from django.urls import path

from .views import trip_plan

urlpatterns = [
    path("trip/", trip_plan, name="trip_plan"),
]