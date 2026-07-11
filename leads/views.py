from django.db import transaction
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser, IsAuthenticated   # add IsAdminUser

from .csv_import import parse_csv_text
from .models import Activity, Lead
from .pagination import LeadPagination
from .serializers import (
    ActivitySerializer,
    CSVImportResultSerializer,
    LeadDetailSerializer,
    LeadSerializer,
)


def is_admin(user):
    """Admins see and touch everything. Everyone else is confined to the leads
    they own. `is_staff` is included deliberately so you can grant full access
    from the Django admin UI without handing out `is_superuser`."""
    return user.is_superuser or user.is_staff


def scope_leads(queryset, user):
    """Row-level access control. This is the ONLY place lead visibility is
    decided — every view below routes through it, so there's no way to add an
    endpoint that accidentally leaks another SPOC's leads.

    Note leads with owner_user=None (Owner Email in the CSV didn't match any
    account) are visible to admins only. That's intentional: an unassigned
    lead being silently invisible is far better than it being visible to
    everyone.
    """
    if is_admin(user):
        return queryset
    return queryset.filter(owner_user=user)


def scope_activities(queryset, user):
    if is_admin(user):
        return queryset
    return queryset.filter(lead__owner_user=user)


class ImportLeadsCSVView(APIView):
    """
    POST /api/leads/import-csv/

    Accepts EITHER:
      - multipart/form-data with a 'file' field (CSV upload), OR
      - JSON / form body with a 'csv_text' field (pasted Excel/CSV rows)

    Owner Email in the CSV is matched (case-insensitively) against User.email
    to set each lead's owner_user. Rows whose email matches no account are
    still imported, but land unassigned — visible to admins only — and are
    reported back in `errors` so nothing disappears silently.
    """

    permission_classes = [IsAdminUser]
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
                    "SPOC, Owner Email, Lead Status, Poll, etc.).",
                    "rows_processed": parsed["row_count"],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            lead_objs = [Lead(**data) for data in parsed["leads"]]
            Lead.objects.bulk_create(lead_objs)

            activity_objs = [Activity(**data) for data in parsed["activities"]]
            Activity.objects.bulk_create(activity_objs)

        # The importer only gets back the leads they can actually see. An
        # ordinary SPOC importing a mixed sheet creates everyone's leads but
        # only sees their own come back — consistent with every other endpoint.
        visible_leads = (
            lead_objs
            if is_admin(request.user)
            else [l for l in lead_objs if l.owner_user_id == request.user.id]
        )
        visible_lead_ids = {l.id for l in visible_leads}
        visible_activities = [a for a in activity_objs if a.lead_id in visible_lead_ids]

        result = {
            "leads_created": len(lead_objs),
            "activities_created": len(activity_objs),
            "rows_processed": parsed["row_count"],
            "errors": parsed["errors"],
            "leads": visible_leads,
            "activities": visible_activities,
        }
        serializer = CSVImportResultSerializer(result)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class LeadListView(generics.ListCreateAPIView):
    """
    GET  /api/leads/  — list leads the caller owns (all of them, if admin),
                         50 per page. Response: {count, next, previous, results}
    POST /api/leads/  — create a lead manually; the caller becomes its owner
    """

    serializer_class = LeadSerializer
    pagination_class = LeadPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return scope_leads(Lead.objects.all(), self.request.user)

    def perform_create(self, serializer):
        # Both fields are set server-side and neither is client-writable:
        # owner_user is the real link, owner is the display name.
        serializer.save(
            owner=self.request.user.username,
            owner_user=self.request.user,
        )


class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/leads/<id>/  — lead profile with its activity timeline
    PATCH  /api/leads/<id>/  — partial update
    DELETE /api/leads/<id>/  — deletes the lead and cascades its activities

    Scoped: requesting a lead you don't own returns 404, not 403 — a 403 would
    confirm the lead exists, which is itself a leak.
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return scope_leads(Lead.objects.all(), self.request.user)

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return LeadSerializer
        return LeadDetailSerializer


class ActivityListView(generics.ListCreateAPIView):
    """
    GET  /api/activities/            — activities on leads the caller owns
    GET  /api/activities/?lead=<id>  — activities for one lead
    POST /api/activities/            — create an activity
    """

    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = scope_activities(Activity.objects.all(), self.request.user)
        lead_id = self.request.query_params.get("lead")
        if lead_id:
            qs = qs.filter(lead_id=lead_id)
        return qs

    def perform_create(self, serializer):
        # Guard the write path too: without this, a SPOC could POST an activity
        # against any lead id they guessed, even one they can't read.
        lead = serializer.validated_data.get("lead")
        if lead and not scope_leads(Lead.objects.filter(pk=lead.pk), self.request.user).exists():
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You don't have access to this lead.")
        serializer.save()


class ActivityDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/activities/<id>/  — single activity
    PATCH  /api/activities/<id>/  — partial update
    DELETE /api/activities/<id>/  — remove an activity
    """

    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return scope_activities(Activity.objects.all(), self.request.user)