import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


# Placeholder values. Confirm the real values before launch and update them
# through the admin settings API rather than changing them in code.
EXAMPLE_SETTINGS = {
    "payment_method": "cod",
    "service_fee_per_order": 5,
    "subscription_monthly": 299,
    "free_months": 1,
    "bill_grace_days": 7,
    "delivery_base_fee": 39,
    "delivery_per_km": 10,
    "senior_pwd_discount_percent": 20,
    "return_fee": 20,
    "limit_new_customer": 1000,
    "limit_regular": 3000,
    "open_orders_new": 1,
    "open_orders_regular": 3,
    "otp_expiry_minutes": 5,
    "session_days": 30,
    "approval_target_days": 2,
    "checkin_lead_minutes": 60,
    "checkin_reminder_minutes": 30,
    "first_order_autopause_minutes": 10,
    "accept_minutes": 5,
    "unusual_confirm_minutes": 5,
    "offer_minutes": 2,
    "offer_max_tries": 3,
    "no_rider_cancel_minutes": 30,
    "pickup_reassign_minutes": 15,
    "failed_calls": 3,
    "failed_wait_minutes": 10,
}


def seed_example_settings(apps, schema_editor):
    Setting = apps.get_model("settings_store", "Setting")
    database = schema_editor.connection.alias
    Setting.objects.using(database).bulk_create(
        [
            Setting(key=key, value=value)
            for key, value in EXAMPLE_SETTINGS.items()
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
