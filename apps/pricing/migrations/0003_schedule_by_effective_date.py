from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("pricing", "0002_seed_price_schedule")]

    operations = [
        migrations.RemoveConstraint(
            model_name="priceschedule",
            name="one_active_schedule_per_season",
        ),
        migrations.AddConstraint(
            model_name="priceschedule",
            constraint=models.UniqueConstraint(
                fields=("season", "effective_from"),
                condition=Q(is_active=True),
                name="one_active_schedule_per_effective_date",
            ),
        ),
    ]
