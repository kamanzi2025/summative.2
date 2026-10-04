from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """One request to a protected endpoint: who made it, what it returned, and which field rules
    applied. Holds record ids only, never coordinates, national IDs or prices."""

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "occurred_at",
            "username",
            "role",
            "method",
            "path",
            "endpoint",
            "status_code",
            "resource",
            "object_ids",
            "coordinate_precision",
            "national_id",
            "commercial_terms",
        ]
        read_only_fields = fields
        extra_kwargs = {
            "object_ids": {"help_text": "Ids of the records returned, or of the record named in the URL."},
            "national_id": {"help_text": "How national IDs were served: last_four or hidden."},
            "commercial_terms": {"help_text": "Whether prices were included; null if the user had no role."},
        }
