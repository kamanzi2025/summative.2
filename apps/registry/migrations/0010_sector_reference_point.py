"""Turn the sector centroids into reference points that no rounding of a plot coordinate can reach.

0007 stored approximate sector centres. A centre sits in the same whole-degree cell as the sector's
plots, so rounding both to 0 or 1 decimal places makes them agree: the point carried the same
coarse location as rounding would. Each point below is moved to a different whole-degree cell from
its sector's plots on *both* axes, so it agrees with no plot coordinate at any precision from 0 to
6 decimal places, however the comparison rounds. The point is a label in coordinate form, not a
location; the sector's name carries the origin. See tests/test_sector_reference_points.py.
"""

from decimal import Decimal

from django.db import migrations, models

# sector: (latitude, longitude). Plots in all six sectors lie in the cells around (-3, 30), (-2, 30)
# or (-3, 29); every point here rounds (0 dp) to a different value on each axis than its plots.
REFERENCE_POINTS = {
    "Kigoma": ("-2.3725", "29.3817"),
    "Mbazi": ("-2.4186", "29.2594"),
    "Kibeho": ("-2.2943", "29.1328"),
    "Ngera": ("-2.2271", "29.3046"),
    "Ruheru": ("-2.1458", "30.6118"),
    "Runda": ("-1.4472", "29.2137"),
}

# The 0007 values, restored on reverse.
PREVIOUS = {
    "Kigoma": ("-2.5560", "29.6880"),
    "Mbazi": ("-2.6160", "29.6730"),
    "Kibeho": ("-2.6380", "29.5560"),
    "Ngera": ("-2.6050", "29.6160"),
    "Ruheru": ("-2.7140", "29.4410"),
    "Runda": ("-1.9950", "29.9850"),
}


def apply(points):
    def run(apps, schema_editor):
        Sector = apps.get_model("registry", "Sector")
        for name, (lat, lon) in points.items():
            Sector.objects.filter(name=name).update(reference_latitude=Decimal(lat), reference_longitude=Decimal(lon))

    return run


class Migration(migrations.Migration):
    dependencies = [("registry", "0009_national_id_not_unique")]

    operations = [
        migrations.RemoveConstraint(model_name="sector", name="sector_centroid_inside_rwanda"),
        migrations.RenameField(model_name="sector", old_name="centroid_latitude", new_name="reference_latitude"),
        migrations.RenameField(model_name="sector", old_name="centroid_longitude", new_name="reference_longitude"),
        migrations.AddConstraint(
            model_name="sector",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("reference_latitude__gte", Decimal("-2.95")),
                    ("reference_latitude__lte", Decimal("-1.04")),
                    ("reference_longitude__gte", Decimal("28.85")),
                    ("reference_longitude__lte", Decimal("30.90")),
                ),
                name="sector_reference_point_inside_rwanda",
            ),
        ),
        migrations.RunPython(apply(REFERENCE_POINTS), apply(PREVIOUS)),
    ]
