from django.urls import path

from .views import PasswordChangeView, UserProfileView, UserRegistrationView

app_name = "users"

urlpatterns = [
    path("register/", UserRegistrationView.as_view(), name="register"),
    path("me/", UserProfileView.as_view(), name="me"),
    path("password/", PasswordChangeView.as_view(), name="password"),
]
