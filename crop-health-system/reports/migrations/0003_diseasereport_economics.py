from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0002_diseasereport_advisory_audio"),
    ]

    operations = [
        migrations.AddField(
            model_name="diseasereport",
            name="econ_expected_yield_value",
            field=models.FloatField(
                blank=True,
                help_text="Full healthy-crop value (₹)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="diseasereport",
            name="econ_current_loss_value",
            field=models.FloatField(
                blank=True,
                help_text="Value already lost to disease (₹)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="diseasereport",
            name="econ_treatment_cost",
            field=models.FloatField(
                blank=True,
                help_text="Estimated treatment cost (₹)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="diseasereport",
            name="econ_expected_recovery",
            field=models.FloatField(
                blank=True,
                help_text="Value recoverable after treatment (₹)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="diseasereport",
            name="econ_net_benefit",
            field=models.FloatField(
                blank=True,
                help_text="Net benefit of treating (₹)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="diseasereport",
            name="econ_roi_pct",
            field=models.FloatField(
                blank=True,
                help_text="Return on treatment investment (%)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="diseasereport",
            name="econ_verdict",
            field=models.CharField(
                blank=True,
                help_text="'TREAT' | 'ACCEPT_LOSS' | 'MONITOR'",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="diseasereport",
            name="econ_rationale",
            field=models.TextField(
                blank=True,
                help_text="Human-readable economic rationale",
            ),
        ),
    ]
