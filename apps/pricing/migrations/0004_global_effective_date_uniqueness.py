from django.db import migrations, models
from django.db.models import Count, Q


def reject_existing_ambiguous_schedules(apps, schema_editor):
    PriceSchedule = apps.get_model("pricing", "PriceSchedule")
    conflicts = (
        PriceSchedule.objects.using(schema_editor.connection.alias)
        .filter(is_active=True)
        .values("effective_from")
        .annotate(schedule_count=Count("pk"))
        .filter(schedule_count__gt=1)
        .order_by("effective_from")
    )
    if conflicts.exists():
        dates = ", ".join(str(row["effective_from"]) for row in conflicts[:10])
        raise RuntimeError(
            "Cannot enforce global price schedule precedence: multiple active schedules exist "
            f"for effective date(s) {dates}. Reconcile them before applying this migration."
        )


class Migration(migrations.Migration):
    dependencies = [("pricing", "0003_schedule_by_effective_date")]

    operations = [
        migrations.RunPython(reject_existing_ambiguous_schedules, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="priceschedule",
            name="one_active_schedule_per_effective_date",
        ),
        migrations.AddConstraint(
            model_name="priceschedule",
            constraint=models.UniqueConstraint(
                fields=("effective_from",),
                condition=Q(is_active=True),
                name="one_active_schedule_per_effective_date",
            ),
        ),
    ]
