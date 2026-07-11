from rest_framework import serializers

from .models import Activity, Lead


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = [
            "id", "lead", "type", "description", "owner",
            "due_date", "time", "lead_status", "completion_status",
            "created_at", "completed_at",
        ]
        read_only_fields = ["id", "created_at"]


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "id", "is_new", "sl_no", "first_name", "last_name", "name",
            "phone", "phone_country_code",
            "secondary_phone", "secondary_phone_country_code",
            "email", "secondary_email",
            "organization", "job_title", "experience",
            "salary", "attended", "time", "result",
            "price_quoted",
            "notes",
            "owner", "owner_email", "status",
            "created_at", "updated_at",
        ]
        # owner is set once on create (from SPOC on import, or whoever creates
        # the lead manually) and can't be reassigned afterwards via the API.
        #
        # phone and email are deliberately NOT read-only: AddLeadModal needs to
        # set them when creating a lead by hand. They're locked in the Lead
        # Profile at the UI level instead.
        #
        # price_quoted and notes are writable — both are set from the Lead
        # Profile / Create Activity modals, which PATCH the lead. Any field
        # missing from the list above is silently dropped by DRF on both read
        # and write, which is exactly how price_quoted was disappearing.
        #
        # owner_user is never client-writable — it's set from Owner Email on
        # import, or from request.user on manual creation. Letting a client set
        # it would let anyone reassign a lead to themselves.
        read_only_fields = [
            "id", "name", "owner", "owner_email", "created_at", "updated_at",
        ]


class LeadDetailSerializer(LeadSerializer):
    activities = ActivitySerializer(many=True, read_only=True)

    class Meta(LeadSerializer.Meta):
        fields = LeadSerializer.Meta.fields + ["activities"]


class CSVImportResultSerializer(serializers.Serializer):
    leads_created = serializers.IntegerField()
    activities_created = serializers.IntegerField()
    rows_processed = serializers.IntegerField()
    errors = serializers.ListField(child=serializers.CharField(), required=False)
    leads = LeadSerializer(many=True)
    activities = ActivitySerializer(many=True)