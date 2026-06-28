import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Creates a superuser if none exists'

    def handle(self, *args, **kwargs):
        User = get_user_model()

        admin_username = os.environ.get('SUPERUSER_USERNAME', 'Admin2')
        admin_email = os.environ.get('SUPERUSER_EMAIL', 'Admin2@profitlynx.com')
        admin_password = os.environ.get('SUPERUSER_PASSWORD', '12345678')
        admin_first_name = os.environ.get('SUPERUSER_FIRST_NAME', 'Admin')
        admin_last_name = os.environ.get('SUPERUSER_LAST_NAME', 'User')
        admin_phone = os.environ.get('SUPERUSER_PHONE', '0000000000')
        admin_country = os.environ.get('SUPERUSER_COUNTRY', 'Unknown')

        existing_superuser = User.objects.filter(is_superuser=True).first()
        if existing_superuser:
            existing_superuser.username = admin_username
            existing_superuser.email = admin_email
            existing_superuser.first_name = admin_first_name
            existing_superuser.last_name = admin_last_name
            existing_superuser.phone = admin_phone
            existing_superuser.country = admin_country
            existing_superuser.is_staff = True
            existing_superuser.is_superuser = True
            existing_superuser.is_active = True
            existing_superuser.set_password(admin_password)
            existing_superuser.save()
            self.stdout.write(self.style.SUCCESS('Existing superuser repaired successfully.'))
            return

        if User.objects.filter(username=admin_username).exists():
            user = User.objects.get(username=admin_username)
            user.email = admin_email
            user.first_name = admin_first_name
            user.last_name = admin_last_name
            user.phone = admin_phone
            user.country = admin_country
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.set_password(admin_password)
            user.save()
            self.stdout.write(self.style.SUCCESS('Existing user upgraded to superuser.'))
            return

        User.objects.create_superuser(
            username=admin_username,
            email=admin_email,
            password=admin_password,
            first_name=admin_first_name,
            last_name=admin_last_name,
            phone=admin_phone,
            country=admin_country,
        )
        self.stdout.write(self.style.SUCCESS('Superuser created successfully.'))
