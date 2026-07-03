from django.db import transaction
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .csv_import import parse_csv_text
from .models import Activity, Lead
from .pagination import LeadPagination
from .serializers import (
    ActivitySerializer,
    CSVImportResultSerializer,
    LeadDetailSerializer,
    LeadSerializer,
)


class ImportLeadsCSVView(APIView):
    """
    POST /api/leads/import-csv/

    Accepts EITHER:
      - multipart/form-data with a 'file' field (CSV upload), OR
      - JSON / form body with a 'csv_text' field (pasted Excel/CSV rows)

    Mirrors the frontend's column mapping: First Name + Last Name -> name,
    each non-empty "Follow up N" column becomes a Follow-up Activity, and
    all imported leads start as New (is_new=True).
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        csv_text = None

        uploaded_file = request.FILES.get("file")
        if uploaded_file:
            try:
                csv_text = uploaded_file.read().decode("utf-8-sig")
            except UnicodeDecodeError:
                return Response(
                    {"detail": "Could not read file as UTF-8 text. Please upload a plain CSV."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            csv_text = request.data.get("csv_text")

        if not csv_text or not csv_text.strip():
            return Response(
                {"detail": "Provide a CSV file under 'file' or pasted rows under 'csv_text'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        parsed = parse_csv_text(csv_text)

        if not parsed["leads"]:
            return Response(
                {
                    "detail": "No leads could be parsed. Check that the header row matches "
                    "the expected columns (First Name, Last Name, Email, Phone Number, "
                    "SPOC, Lead Status, Follow up 1-7, etc.).",
                    "rows_processed": parsed["row_count"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            lead_objs = [Lead(**data) for data in parsed["leads"]]
            Lead.objects.bulk_create(lead_objs)

            activity_objs = [Activity(**data) for data in parsed["activities"]]
            Activity.objects.bulk_create(activity_objs)

        result = {
            "leads_created": len(lead_objs),
            "activities_created": len(activity_objs),
            "rows_processed": parsed["row_count"],
            "errors": parsed["errors"],
            "leads": lead_objs,
            "activities": activity_objs,
        }
        serializer = CSVImportResultSerializer(result)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LeadListView(generics.ListCreateAPIView):
    """
    GET  /api/leads/  — list leads, 50 per page (?page=2, or ?page_size=N up
                         to 200). Response shape: {count, next, previous, results}
    POST /api/leads/  — create a lead manually (owner is read-only here too;
                         set it via the CSV import path or a dedicated field
                         if you need manual assignment on creation)
    """

    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    pagination_class = LeadPagination
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # owner is read-only on LeadSerializer (see serializers.py) so the
        # client can never set it directly — it's always the logged-in user
        # who created the lead, set here server-side.
        serializer.save(owner=self.request.user.username)


class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/leads/<id>/  — lead profile with its activity timeline
    PATCH  /api/leads/<id>/  — partial update (owner is rejected — read-only
                                 on the serializer)
    DELETE /api/leads/<id>/  — deletes the lead and cascades its activities
    """

    queryset = Lead.objects.all()
    serializer_class = LeadDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        # Reads return the full detail shape (with activities); writes use
        # the plain LeadSerializer since activities aren't written here.
        if self.request.method in ("PUT", "PATCH"):
            return LeadSerializer
        return LeadDetailSerializer


class ActivityListView(generics.ListCreateAPIView):
    """
    GET  /api/activities/            — list all activities
    GET  /api/activities/?lead=<id>  — activities for one lead
    POST /api/activities/            — create an activity
    """

    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Activity.objects.all()
        lead_id = self.request.query_params.get("lead")
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        return qs


class ActivityDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/activities/<id>/  — single activity
    PATCH  /api/activities/<id>/  — partial update (e.g. mark Completed)
    DELETE /api/activities/<id>/  — remove an activity
    """

    queryset = Activity.objects.all()
    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]