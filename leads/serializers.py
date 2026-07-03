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
            "phone", "email", "organization", "job_title", "experience",
            "salary", "attended", "time", "result", "owner", "status",
            "created_at", "updated_at",
        ]
        # owner is set once on create (from SPOC on import, or whoever creates
        # the lead manually) and can't be reassigned afterwards via the API.
        read_only_fields = ["id", "name", "owner", "created_at", "updated_at"]


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