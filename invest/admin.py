from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, InvestmentTier, CryptoCurrency, Investment, Transaction,
    DepositRequest, WithdrawalRequest, CryptoPrice
)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = (
        'username', 'email', 'first_name', 'last_name', 'phone', 'country',
        'balance', 'total_deposited', 'total_withdrawn', 'total_profit',
        'referral_code', 'is_verified', 'date_joined'
    )
    list_filter = ('is_verified', 'is_staff', 'is_superuser', 'country')
    search_fields = ('username', 'email', 'phone', 'referral_code')
    readonly_fields = ('date_joined',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Investment Info', {
            'fields': (
                'balance', 'total_deposited', 'total_withdrawn',
                'total_profit', 'referral_code', 'referred_by', 'is_verified'
            )
        }),
    )

@admin.register(InvestmentTier)
class InvestmentTierAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'roi_percentage', 'duration_days',
        'min_investment', 'max_investment', 'referral_bonus',
        'capital_return', 'is_active'
    )
    list_filter = ('is_active', 'capital_return')
    search_fields = ('name',)

@admin.register(CryptoCurrency)
class CryptoCurrencyAdmin(admin.ModelAdmin):
    list_display = ('name', 'symbol', 'wallet_address', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'symbol')

@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'amount', 'start_date', 'end_date', 'is_completed', 'profit_earned')
    list_filter = ('is_completed', 'tier')
    search_fields = ('user__username', 'tier__name')

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'transaction_type', 'amount', 'status', 'created_at',
        'cryptocurrency', 'investment_tier'
    )
    list_filter = ('transaction_type', 'status', 'cryptocurrency')
    search_fields = ('user__username', 'transaction_id', 'wallet_address')
    date_hierarchy = 'created_at'

@admin.register(DepositRequest)
class DepositRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'amount', 'cryptocurrency', 'investment_tier',
        'status', 'created_at', 'processed_by'
    )
    list_filter = ('status', 'cryptocurrency')
    search_fields = ('user__username', 'transaction_id')
    date_hierarchy = 'created_at'

@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'amount', 'cryptocurrency', 'wallet_address',
        'status', 'created_at', 'processed_by'
    )
    list_filter = ('status', 'cryptocurrency')
    search_fields = ('user__username', 'wallet_address')
    date_hierarchy = 'created_at'

@admin.register(CryptoPrice)
class CryptoPriceAdmin(admin.ModelAdmin):
    list_display = ('cryptocurrency', 'price_usd', 'change_24h', 'last_updated')
    search_fields = ('cryptocurrency__symbol',)
    date_hierarchy = 'last_updated'
