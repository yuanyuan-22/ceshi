from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("qa", "0002_alter_qatask_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="qatask",
            name="auto_accuracy",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qatask",
            name="auto_completeness",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="qatask",
            name="auto_judge_raw",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="qatask",
            name="auto_relevance",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
