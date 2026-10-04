"""Give every seeded sector a reference point: the location exporters receive instead of a plot's.

The points are approximate centres of each sector, to about 0.01 degrees (~1 km), not surveyed
centroids. That is enough for their job: every plot in a sector reports the same point, so a
partner learns the sector and nothing finer. They are stored to 4 decimal places on purpose, and
no point equals any rounding (0-6 decimal places) of an F2 fixture coordinate; see
tests/test_sector_centroids.py.
"""

from decimal import Decimal

from django.db import migrations

# sector: (latitude, longitude)
CENTROIDS = {
    "Kigoma": ("-2.5560", "29.6880"),
    "Mbazi": ("-2.6160", "29.6730"),
    "Kibeho": ("-2.6380", "29.5560"),
    "Ngera": ("-2.6050", "29.6160"),
    "Ruheru": ("-2.7140", "29.4410"),
    "Runda": ("-1.9950", "29.9850"),
}


def seed(apps, schema_editor):
    Sector = apps.get_model("registry", "Sector")
    for name, (lat, lon) in CENTROIDS.items():
        Sector.objects.filter(name=name).update(centroid_latitude=Decimal(lat), centroid_longitude=Decimal(lon))
    missing = list(Sector.objects.filter(centroid_latitude__isnull=True).values_list("name", flat=True))
    if missing:
        # The next migration makes the centroid required; stop here with a clear message instead.
        raise RuntimeError(f"Add a centroid for these sectors to 0007_seed_sector_centroids: {missing}")


def unseed(apps, schema_editor):
    apps.get_model("registry", "Sector").objects.update(centroid_latitude=None, centroid_longitude=None)


class Migration(migrations.Migration):
    dependencies = [("registry", "0006_sector_centroid")]

    operations = [migrations.RunPython(seed, unseed)]
