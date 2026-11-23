import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CashRecord",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("customer_payment", "Customer payment"),
                            ("change", "Change"),
                            ("shop_payout", "Shop payout"),
                            ("delivery_payment", "Delivery payment"),
                            ("correction", "Correction"),
                        ],
                        max_length=30,
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "from_party",
                    models.CharField(
                        choices=[
                            ("customer", "Customer"),
                            ("rider", "Rider"),
                            ("shop", "Shop"),
                            ("platform", "Platform"),
                            ("coordinator", "Area coordinator"),
                        ],
                        db_column="from",
                        max_length=20,
                    ),
                ),
                (
                    "to_party",
                    models.CharField(
                        choices=[
                            ("customer", "Customer"),
                            ("rider", "Rider"),
                            ("shop", "Shop"),
                            ("platform", "Platform"),
                            ("coordinator", "Area coordinator"),
                        ],
                        db_column="to",
                        max_length=20,
                    ),
                ),
                ("reason", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cash_records_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="cash_records",
                        to="orders.order",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "pk"]},
        ),
        migrations.AddConstraint(
            model_name="cashrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gt", 0)),
                name="cash_record_amount_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="cashrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("from_party", models.F("to_party")), _negated=True),
                name="cash_record_parties_differ",
            ),
        ),
        migrations.AddConstraint(
            model_name="cashrecord",
            constraint=models.CheckConstraint(
                condition=models.Q(("type", "correction"), _negated=True)
                | models.Q(("reason", ""), _negated=True),
                name="cash_correction_has_reason",
            ),
        ),
    ]
