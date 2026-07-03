"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path

from .frontend_views import ReactAppView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('leads.urls')),

    # Catch-all MUST be last: Django tries urlpatterns top-to-bottom and
    # stops at the first match, so this only ever fires for routes that
    # /admin/ and /api/... didn't already claim (in practice, just "/").
    re_path(r'^.*$', ReactAppView.as_view(), name='react-app'),
]