from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("user", "User"),
                    ("expert", "Expert"),
                    ("admin", "Admin"),
                ],
                default="user",
                max_length=16,
                verbose_name="Role",
            ),
        ),
    ]
