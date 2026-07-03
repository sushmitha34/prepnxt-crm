from django.http import HttpResponse
from django.views.generic import View
from pathlib import Path
from django.conf import settings


class ReactAppView(View):
    """
    Serves the built React app's index.html for any route not already
    claimed by the DRF API urlpatterns (which are matched first — Django
    tries urlpatterns in order, so as long as api/... patterns are listed
    before this catch-all in config/urls.py, this never intercepts them).

    This app doesn't use client-side URL routing (it's tab-state-based, see
    CRMContext's currentPage), so in practice this only really matters for
    the root "/" — but it's here so a browser refresh never 404s regardless.
    """

    def get(self, request, *args, **kwargs):
        index_path = Path(settings.FRONTEND_BUILD_DIR) / "index.html"
        try:
            with open(index_path, encoding="utf-8") as f:
                return HttpResponse(f.read(), content_type="text/html")
        except FileNotFoundError:
            return HttpResponse(
                "Frontend build not found. Run `npm run build` in the "
                "frontend folder, then restart the Django server.",
                status=501,
            )