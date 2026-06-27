from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

class Command(BaseCommand):
    help = 'Process daily profits for all active investments'

    def handle(self, *args, **options):
        from invest.models import Investment, Transaction, User
        today = timezone.now().date()
        processed = 0
        errors = 0

        active_investments = Investment.objects.filter(is_completed=False).select_related('user', 'tier')

        for inv in active_investments:
            try:
                last_profit = inv.last_profit_date if hasattr(inv, 'last_profit_date') and inv.last_profit_date else inv.start_date.date()
                days_due = (today - last_profit).days
                if days_due <= 0:
                    continue

                end_date = inv.start_date.date() + timedelta(days=inv.tier.duration_days)
                days_left = (end_date - last_profit).days
                days_to_credit = min(days_due, days_left)

                if days_to_credit > 0:
                    daily_profit = (inv.amount * inv.tier.roi_percentage / Decimal('100')) / inv.tier.duration_days
                    total_profit = daily_profit * days_to_credit

                    # Create profit transaction
                    Transaction.objects.create(
                        user=inv.user,
                        transaction_type='PROFIT',
                        amount=total_profit,
                        status='COMPLETED',
                        investment_tier=inv.tier,
                        notes=f'Daily profit for {days_to_credit} day(s) - Investment #{inv.id}'
                    )

                    # Update user balance
                    inv.user.update_balances()
                    inv.profit_earned += total_profit

                if hasattr(inv, 'last_profit_date'):
                    inv.last_profit_date = today

                if today >= end_date:
                    inv.is_completed = True
                    self.stdout.write(f'Completed investment #{inv.id} for {inv.user.username}')

                inv.save()
                processed += 1
            except Exception as e:
                errors += 1
                self.stderr.write(f'Error processing investment #{inv.id}: {e}')

        self.stdout.write(self.style.SUCCESS(f'Processed {processed} investments. Errors: {errors}'))
