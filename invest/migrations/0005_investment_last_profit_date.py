from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('invest', '0004_investmenttier_capital_return'),
    ]
    operations = [
        migrations.AddField(
            model_name='investment',
            name='last_profit_date',
            field=models.DateField(null=True, blank=True),
        ),
    ]
