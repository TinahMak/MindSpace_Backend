"""
URL configuration for mindspace project.

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
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('chat/', include('aichat.urls')),
    path('wellness/', include('wellness.urls')),
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# ── v10 mobile API (added by patch_v10.py) ──
from django.urls import include as _v10_include, path as _v10_path  # noqa: E402

urlpatterns += [_v10_path("api/v1/", _v10_include("api.urls"))]


# ── v12 admin panel (added by patch_v12.py) ──
from django.urls import include as _v12_include, path as _v12_path  # noqa: E402

urlpatterns += [_v12_path("panel/", _v12_include("adminpanel.urls"))]
