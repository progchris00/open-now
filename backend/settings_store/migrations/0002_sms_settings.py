from django.db import migrations

SMS_SETTINGS = {
    "sms_max_retries": 3,
    "sms_retry_backoff_seconds": 30,
    "sms_retry_backoff_multiplier": 2,
    "sms_request_timeout_seconds": 10,
}


def seed_sms_settings(apps, schema_editor):
    Setting = apps.get_model("settings_store", "Setting")
    database = schema_editor.connection.alias
    Setting.objects.using(database).bulk_create(
        [Setting(key=key, value=value) for key, value in SMS_SETTINGS.items()]
    )


def remove_sms_settings(apps, schema_editor):
    Setting = apps.get_model("settings_store", "Setting")
    Setting.objects.using(schema_editor.connection.alias).filter(
        key__in=SMS_SETTINGS
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("settings_store", "0001_initial")]

    operations = [
        migrations.RunPython(seed_sms_settings, reverse_code=remove_sms_settings)
    ]
