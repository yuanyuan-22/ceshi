from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("evaluation", "0002_rename_eval_evalresult_run_found_idx_evaluation__run_id_1b187d_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="evalrun",
            name="eval_mode",
            field=models.CharField(blank=True, default="easy", max_length=16),
        ),
    ]
