from django.urls import path

from .views import CSRFTokenView, UserLoginView, UserLogoutView

app_name = "auth"

urlpatterns = [
    path("csrf/", CSRFTokenView.as_view(), name="csrf"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
]
