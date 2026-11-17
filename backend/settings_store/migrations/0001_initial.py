import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_example_settings(apps, schema_editor):
    Setting = apps.get_model("settings_store", "Setting")
    database = schema_editor.connection.alias
    Setting.objects.using(database).bulk_create(
        [
            Setting(key="service_fee_per_order", value=5),
            Setting(key="payment_method", value="cod"),
        ]
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Setting",
            fields=[
                (
                    "key",
                    models.CharField(
                        max_length=100,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("value", models.JSONField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_settings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["key"],
            },
        ),
        migrations.RunPython(seed_example_settings, migrations.RunPython.noop),
    ]
