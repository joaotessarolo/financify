from django.urls import path

from .views import UserProfileView, UserRegistrationView

app_name = "users"

urlpatterns = [
    path("register/", UserRegistrationView.as_view(), name="register"),
    path("me/", UserProfileView.as_view(), name="me"),
]
