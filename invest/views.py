from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Q, Count
from decimal import Decimal
import requests
from .models import (
    User, InvestmentTier, CryptoCurrency, Investment,
    Transaction, DepositRequest, WithdrawalRequest, CryptoPrice
)
from datetime import timedelta
from django.core.mail import send_mail
from django.views.decorators.csrf import csrf_exempt
import json

from .models import *

# ─── Landing pages ─────────────────────────────────────────────────────────────
def home(request):
    tiers = InvestmentTier.objects.filter(is_active=True).order_by('min_investment')
    return render(request, "landing/index.html", {'investment_tiers': tiers})

def about(request):
    return render(request, "landing/about.html")

def faq(request):
    return render(request, "landing/faq.html")

def package(request):
    tiers = InvestmentTier.objects.filter(is_active=True).order_by('min_investment')
    return render(request, "landing/package.html", {'investment_tiers': tiers})

def privacy(request):
    return render(request, "landing/privacy.html")

def terms(request):
    return render(request, "landing/rules.html")

def contact(request):
    return render(request, "landing/support.html")

# ─── Auth ───────────────────────────────────────────────────────────────────────
def signin(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, "landing/login.html")

def signup(request):
    if request.method == 'POST':
        first_name = request.POST.get('fname')
        last_name  = request.POST.get('lname')
        username   = request.POST.get('username')
        email      = request.POST.get('email')
        password   = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        phone   = request.POST.get('phone')
        country = request.POST.get('country')

        if password != password_confirm:
            messages.error(request, 'Passwords do not match')
            return render(request, "landing/register.html")
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return render(request, "landing/register.html")
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return render(request, "landing/register.html")

        ref_code = request.GET.get('ref') or request.POST.get('ref', '').strip()
        referred_by_user = None
        if ref_code:
            try:
                referred_by_user = User.objects.get(referral_code=ref_code)
            except User.DoesNotExist:
                pass

        try:
            user = User.objects.create_user(
                username=username, email=email, password=password,
                first_name=first_name, last_name=last_name,
                phone=phone, country=country, referred_by=referred_by_user
            )
            messages.success(request, 'Account created successfully! Please login.')
            return redirect('signin')
        except Exception:
            messages.error(request, 'Error creating account. Please try again.')

    return render(request, "landing/register.html")

@login_required
def user_logout(request):
    logout(request)
    return redirect('home')

# ─── Profit processing helper ────────────────────────────────────────────────────
def _process_user_profits(user):
    today = timezone.now().date()
    active = Investment.objects.filter(user=user, is_completed=False).select_related('tier')
    for inv in active:
        try:
            last = inv.last_profit_date or inv.start_date.date()
            days_due = (today - last).days
            if days_due <= 0:
                continue
            end_date = inv.start_date.date() + timedelta(days=inv.tier.duration_days)
            days_left = (end_date - last).days
            days_to_credit = min(days_due, days_left)
            if days_to_credit > 0:
                daily = (inv.amount * inv.tier.roi_percentage / Decimal('100')) / inv.tier.duration_days
                total = daily * days_to_credit
                Transaction.objects.create(
                    user=user, transaction_type='PROFIT', amount=total,
                    status='COMPLETED', investment_tier=inv.tier,
                    notes=f'Daily profit for {days_to_credit} day(s) on Investment #{inv.id}'
                )
                inv.profit_earned += total
            inv.last_profit_date = today
            if today >= end_date:
                inv.is_completed = True
            inv.save(update_fields=['last_profit_date', 'profit_earned', 'is_completed'])
            user.update_balances()
        except Exception:
            pass

# ─── User dashboard ──────────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    user = request.user
    _process_user_profits(user)
    update_crypto_prices()

    active_investments = Investment.objects.filter(user=user, is_completed=False).select_related('tier')
    recent_deposits    = DepositRequest.objects.filter(user=user).order_by('-created_at')[:5]
    recent_withdrawals = WithdrawalRequest.objects.filter(user=user).order_by('-created_at')[:5]
    referral_link  = request.build_absolute_uri(f'/signup?ref={user.referral_code}')
    referral_count = User.objects.filter(referred_by=user).count()

    context = {
        'user': user, 'profile': user,
        'total_deposited': user.current_total_deposited,
        'total_profit': user.current_total_profit,
        'total_withdrawn': user.current_total_withdrawn,
        'total_balance': user.current_balance,
        'active_investments': active_investments,
        'active_count': active_investments.count(),
        'recent_transactions': user.transactions.all()[:5],
        'recent_deposits': recent_deposits,
        'recent_withdrawals': recent_withdrawals,
        'crypto_prices': CryptoPrice.objects.filter(cryptocurrency__symbol__in=['BTC','ETH','USDT','TON'])[:4],
        'referral_link': referral_link,
        'referral_count': referral_count,
    }
    return render(request, 'invest/dashboard.html', context)

# ─── Deposit ─────────────────────────────────────────────────────────────────────
@login_required
def deposit(request):
    if request.method == 'POST':
        try:
            amount       = Decimal(request.POST.get('amount', 0))
            crypto_id    = request.POST.get('cryptocurrency')
            tier_name    = request.POST.get('selected_tier', '').strip().upper()
            transaction_id = request.POST.get('transaction_id', '').strip()

            if not all([amount, crypto_id, tier_name, transaction_id]):
                messages.error(request, 'All fields are required.')
                return redirect('deposit')
            if amount <= 0:
                messages.error(request, 'Please enter a valid amount.')
                return redirect('deposit')

            cryptocurrency = get_object_or_404(CryptoCurrency, id=crypto_id)
            if not cryptocurrency.wallet_address:
                messages.error(request, f'{cryptocurrency.name} wallet address not configured. Contact admin.')
                return redirect('deposit')

            try:
                investment_tier = InvestmentTier.objects.get(name=tier_name, is_active=True)
            except InvestmentTier.DoesNotExist:
                messages.error(request, 'Invalid investment plan selected.')
                return redirect('deposit')

            if amount < investment_tier.min_investment:
                messages.error(request, f'Minimum for {investment_tier.name} is ${investment_tier.min_investment:,.2f}')
                return redirect('deposit')
            if investment_tier.max_investment and amount > investment_tier.max_investment:
                messages.error(request, f'Maximum for {investment_tier.name} is ${investment_tier.max_investment:,.2f}')
                return redirect('deposit')

            if Transaction.objects.filter(transaction_id=transaction_id).exists():
                messages.error(request, 'This transaction ID has already been used.')
                return redirect('deposit')

            DepositRequest.objects.create(
                user=request.user, amount=amount, cryptocurrency=cryptocurrency,
                investment_tier=investment_tier, transaction_id=transaction_id,
                wallet_address_used=cryptocurrency.wallet_address
            )
            Transaction.objects.create(
                user=request.user, transaction_type='DEPOSIT', amount=amount,
                cryptocurrency=cryptocurrency, transaction_id=transaction_id,
                investment_tier=investment_tier, status='PENDING'
            )
            messages.success(request, 'Deposit submitted! Awaiting admin approval.')
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
            return redirect('deposit')

    context = {
        'cryptocurrencies': CryptoCurrency.objects.filter(is_active=True, symbol__in=['BTC','ETH','USDT','TON','SOL']),
        'investment_tiers': InvestmentTier.objects.filter(is_active=True).order_by('min_investment'),
    }
    return render(request, 'invest/deposit.html', context)

# ─── Withdraw ────────────────────────────────────────────────────────────────────
@login_required
def withdraw(request):
    if request.method == 'POST':
        try:
            amount       = Decimal(request.POST.get('amount', 0))
            crypto_id    = request.POST.get('cryptocurrency')
            wallet_address = request.POST.get('wallet_address')

            if amount > request.user.current_balance:
                messages.error(request, 'Insufficient balance')
                return redirect('withdraw')

            cryptocurrency = CryptoCurrency.objects.get(id=crypto_id)
            WithdrawalRequest.objects.create(
                user=request.user, amount=amount,
                cryptocurrency=cryptocurrency, wallet_address=wallet_address
            )
            Transaction.objects.create(
                user=request.user, transaction_type='WITHDRAWAL', amount=amount,
                cryptocurrency=cryptocurrency, wallet_address=wallet_address, status='PENDING'
            )
            messages.success(request, 'Withdrawal request submitted! Awaiting admin approval.')
            return redirect('dashboard')
        except Exception:
            messages.error(request, 'Error processing withdrawal. Please try again.')

    context = {
        'cryptocurrencies': CryptoCurrency.objects.filter(is_active=True, symbol__in=['BTC','ETH','USDT','TON','SOL']),
        'user_balance': request.user.current_balance,
    }
    return render(request, 'invest/withdraw.html', context)

# ─── History ─────────────────────────────────────────────────────────────────────
@login_required
def history(request):
    context = {
        'transactions': request.user.transactions.all().order_by('-created_at'),
        'deposit_requests': request.user.deposit_requests.all().order_by('-created_at'),
        'withdrawal_requests': request.user.withdrawal_requests.all().order_by('-created_at'),
    }
    return render(request, 'invest/history.html', context)

# ─── Profile ─────────────────────────────────────────────────────────────────────
@login_required
def profile(request):
    if request.method == 'POST':
        if request.headers.get('Content-Type') == 'application/json':
            try:
                data = json.loads(request.body)
                if not request.user.check_password(data.get('current_password', '')):
                    return JsonResponse({'success': False, 'message': 'Current password is incorrect'})
                np = data.get('new_password', '')
                if len(np) < 8:
                    return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters'})
                request.user.set_password(np)
                request.user.save()
                update_session_auth_hash(request, request.user)
                return JsonResponse({'success': True, 'message': 'Password changed successfully'})
            except Exception:
                return JsonResponse({'success': False, 'message': 'An error occurred'})
        else:
            try:
                request.user.first_name = request.POST.get('first_name', '')
                request.user.last_name  = request.POST.get('last_name', '')
                request.user.email      = request.POST.get('email', '')
                if hasattr(request.user, 'phone'):
                    request.user.phone = request.POST.get('phone', '')
                if hasattr(request.user, 'country'):
                    request.user.country = request.POST.get('country', '')
                request.user.save()
                return JsonResponse({'success': True, 'message': 'Profile updated successfully'})
            except Exception:
                return JsonResponse({'success': False, 'message': 'Error updating profile'})
    return render(request, 'invest/profile.html', {'user': request.user})

# ─── Investments list ────────────────────────────────────────────────────────────
@login_required
def investments(request):
    context = {'investments': Investment.objects.filter(user=request.user).select_related('tier')}
    return render(request, 'invest/investments.html', context)

# ─── AJAX wallet address ──────────────────────────────────────────────────────────
@login_required
def get_wallet_address(request):
    if request.method == 'GET':
        try:
            c = CryptoCurrency.objects.get(id=request.GET.get('crypto_id'))
            return JsonResponse({'success': True, 'wallet_address': c.wallet_address, 'crypto_name': c.name})
        except CryptoCurrency.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Not found'})
    return JsonResponse({'success': False})

# ─── Crypto price updater ─────────────────────────────────────────────────────────
def update_crypto_prices():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {'ids': 'bitcoin,ethereum,solana,the-open-network', 'vs_currencies': 'usd', 'include_24hr_change': 'true'}
        data = requests.get(url, params=params, timeout=10).json()
        mapping = {'bitcoin':'BTC','ethereum':'ETH','solana':'SOL','the-open-network':'TON'}
        for api_id, symbol in mapping.items():
            if api_id in data:
                crypto, _ = CryptoCurrency.objects.get_or_create(symbol=symbol, defaults={'name': symbol, 'wallet_address': '', 'is_active': True})
                CryptoPrice.objects.update_or_create(
                    cryptocurrency=crypto,
                    defaults={'price_usd': Decimal(str(data[api_id]['usd'])), 'change_24h': Decimal(str(data[api_id].get('usd_24h_change', 0))), 'last_updated': timezone.now()}
                )
    except Exception:
        pass

# ─── Admin helpers ────────────────────────────────────────────────────────────────
def is_admin(user):
    return user.is_staff or user.is_superuser

# ─── Admin dashboard ──────────────────────────────────────────────────────────────
@user_passes_test(is_admin)
def admin_dashboard(request):
    context = {
        'total_users': User.objects.filter(is_staff=False).count(),
        'pending_deposits': DepositRequest.objects.filter(status='PENDING').count(),
        'pending_withdrawals': WithdrawalRequest.objects.filter(status='PENDING').count(),
        'total_deposits_today': DepositRequest.objects.filter(created_at__date=timezone.now().date(), status='APPROVED').aggregate(total=Sum('amount'))['total'] or 0,
        'recent_deposits': DepositRequest.objects.select_related('user','cryptocurrency','investment_tier').order_by('-created_at')[:10],
    }
    return render(request, 'admins/admin_dashboard.html', context)

# ─── Admin deposits ───────────────────────────────────────────────────────────────
@user_passes_test(is_admin)
def admin_deposits(request):
    if request.method == 'POST':
        deposit_id = request.POST.get('deposit_id')
        action = request.POST.get('action')
        try:
            deposit = get_object_or_404(DepositRequest, id=deposit_id)
            if action == 'approve':
                deposit.status = 'APPROVED'
                deposit.processed_at = timezone.now()
                deposit.processed_by = request.user
                deposit.save()
                user = deposit.user
                user.update_balances()
                Investment.objects.create(
                    user=user, tier=deposit.investment_tier, amount=deposit.amount,
                    start_date=timezone.now(), end_date=timezone.now() + timedelta(days=deposit.investment_tier.duration_days)
                )
                Transaction.objects.filter(user=user, transaction_type='DEPOSIT', amount=deposit.amount, status='PENDING', transaction_id=deposit.transaction_id).update(status='APPROVED', processed_at=timezone.now())
                if user.referred_by:
                    bonus = (deposit.amount * deposit.investment_tier.referral_bonus) / 100
                    Transaction.objects.create(user=user.referred_by, transaction_type='REFERRAL', amount=bonus, status='COMPLETED', notes=f'Referral bonus from {user.username}')
                    user.referred_by.update_balances()
                messages.success(request, f'Deposit of ${deposit.amount} approved for {user.username}')
            elif action == 'reject':
                deposit.status = 'REJECTED'
                deposit.processed_at = timezone.now()
                deposit.processed_by = request.user
                deposit.save()
                Transaction.objects.filter(user=deposit.user, transaction_type='DEPOSIT', amount=deposit.amount, status='PENDING', transaction_id=deposit.transaction_id).update(status='REJECTED', processed_at=timezone.now())
                messages.success(request, f'Deposit rejected for {deposit.user.username}')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        return redirect('admin_deposits')

    deposits = DepositRequest.objects.select_related('user','cryptocurrency','investment_tier','processed_by').order_by('-created_at')
    today = timezone.now().date()
    stats = DepositRequest.objects.aggregate(
        total_pending=Sum('amount', filter=Q(status='PENDING')),
        approved_today=Count('id', filter=Q(processed_at__date=today, status='APPROVED')),
        rejected_today=Count('id', filter=Q(processed_at__date=today, status='REJECTED')),
    )
    context = {'deposits': deposits, 'total_pending': stats['total_pending'] or 0, 'approved_today': stats['approved_today'], 'rejected_today': stats['rejected_today'], 'total_count': deposits.count()}
    return render(request, 'admins/deposits.html', context)

# ─── Admin add funds ──────────────────────────────────────────────────────────────
@user_passes_test(is_admin)
def add_funds(request):
    users = User.objects.filter(is_staff=False).order_by('username')
    if request.method == 'POST':
        user_id    = request.POST.get('user')
        amount_raw = request.POST.get('amount')
        note       = request.POST.get('note', '').strip()
        if not user_id:
            messages.error(request, 'Please select a user.')
            return redirect('add_funds')
        try:
            amount = Decimal(amount_raw)
        except (TypeError, InvalidOperation):
            messages.error(request, 'Invalid amount.')
            return redirect('add_funds')
        if amount <= 0:
            messages.error(request, 'Amount must be greater than 0.')
            return redirect('add_funds')
        user = get_object_or_404(User, pk=user_id)
        try:
            with transaction.atomic():
                Transaction.objects.create(user=user, transaction_type='DEPOSIT', amount=amount, status='APPROVED', notes=note)
                user.update_balances()
        except Exception as e:
            messages.error(request, f'Error: {e}')
            return redirect('add_funds')
        messages.success(request, f'Successfully added ${amount} to {user.username}.')
        return redirect('admin_dashboard')
    return render(request, 'admins/add_funds.html', {'users': users})

# ─── Admin investments ────────────────────────────────────────────────────────────
@user_passes_test(is_admin)
def admin_investments(request):
    if request.method == 'POST':
        investment_id = request.POST.get('investment_id')
        action = request.POST.get('action')
        try:
            inv = get_object_or_404(Investment, id=investment_id)
            if action == 'add_profit':
                profit_amount = Decimal(request.POST.get('profit_amount', '0'))
                if profit_amount > 0:
                    inv.profit_earned += profit_amount
                    inv.save()
                    Transaction.objects.create(user=inv.user, transaction_type='PROFIT', amount=profit_amount, status='COMPLETED', investment_tier=inv.tier, notes='Profit added by admin')
                    inv.user.update_balances()
                    messages.success(request, f'Added ${profit_amount} profit to {inv.user.username}')
            elif action == 'complete':
                inv.is_completed = True
                inv.save()
                messages.success(request, f'Investment completed for {inv.user.username}')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        return redirect('admin_investments')

    investments = Investment.objects.select_related('user','tier').order_by('-start_date')
    stats = investments.aggregate(total_invested=Sum('amount'), total_profits=Sum('profit_earned'), active_count=Count('id', filter=Q(is_completed=False)), completed_count=Count('id', filter=Q(is_completed=True)))
    context = {'investments': investments, **stats}
    return render(request, 'admins/investments.html', context)

# ─── Admin wallet settings ────────────────────────────────────────────────────────
@user_passes_test(is_admin)
def admin_settings(request):
    crypto_data = {'BTC': 'Bitcoin', 'ETH': 'Ethereum', 'TON': 'Toncoin', 'SOL': 'Solana'}
    if request.method == 'POST':
        try:
            for symbol, name in crypto_data.items():
                wallet = request.POST.get(f'{symbol.lower()}_wallet', '').strip()
                if wallet:
                    crypto, _ = CryptoCurrency.objects.get_or_create(symbol=symbol, defaults={'name': name, 'wallet_address': '', 'is_active': True})
                    crypto.wallet_address = wallet
                    crypto.save()
            messages.success(request, 'Wallet addresses updated successfully!')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        return redirect('admin_settings')

    cryptocurrencies = {}
    for symbol, name in crypto_data.items():
        crypto, _ = CryptoCurrency.objects.get_or_create(symbol=symbol, defaults={'name': name, 'wallet_address': '', 'is_active': True})
        cryptocurrencies[name.lower()] = crypto
    return render(request, 'admins/settings.html', {'cryptocurrencies': cryptocurrencies})

# ─── Admin withdrawals ────────────────────────────────────────────────────────────
@user_passes_test(is_admin)
def admin_withdrawals(request):
    if request.method == 'POST':
        withdrawal_id = request.POST.get('withdrawal_id')
        action = request.POST.get('action')
        try:
            w = get_object_or_404(WithdrawalRequest, id=withdrawal_id)
            if action == 'approve':
                w.status = 'APPROVED'
                w.processed_at = timezone.now()
                w.processed_by = request.user
                w.save()
                Transaction.objects.filter(user=w.user, transaction_type='WITHDRAWAL', amount=w.amount, status='PENDING').update(status='APPROVED', processed_at=timezone.now())
                w.user.update_balances()
                messages.success(request, f'Withdrawal of ${w.amount} approved for {w.user.username}')
            elif action == 'reject':
                w.status = 'REJECTED'
                w.processed_at = timezone.now()
                w.processed_by = request.user
                w.save()
                Transaction.objects.filter(user=w.user, transaction_type='WITHDRAWAL', amount=w.amount, status='PENDING').update(status='REJECTED', processed_at=timezone.now())
                w.user.update_balances()
                messages.success(request, f'Withdrawal of ${w.amount} rejected for {w.user.username}')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        return redirect('admin_withdrawals')

    withdrawals = WithdrawalRequest.objects.select_related('user','cryptocurrency','processed_by').order_by('-created_at')
    today = timezone.now().date()
    stats = withdrawals.aggregate(
        total_pending=Sum('amount', filter=Q(status='PENDING')),
        approved_today=Count('id', filter=Q(processed_at__date=today, status='APPROVED')),
        rejected_today=Count('id', filter=Q(processed_at__date=today, status='REJECTED')),
    )
    context = {'withdrawals': withdrawals, 'total_pending': stats['total_pending'] or 0, 'approved_today': stats['approved_today'] or 0, 'rejected_today': stats['rejected_today'] or 0, 'total_count': withdrawals.count()}
    return render(request, 'admins/withdrawals.html', context)

# ─── Admin users ──────────────────────────────────────────────────────────────────
@user_passes_test(is_admin)
def admin_users(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        action  = request.POST.get('action')
        try:
            u = get_object_or_404(User, id=user_id)
            if action == 'delete':
                if u.is_superuser or u.is_staff:
                    messages.error(request, 'Cannot delete admin users')
                else:
                    username = u.username
                    u.delete()
                    messages.success(request, f'User {username} deleted successfully')
        except Exception as e:
            messages.error(request, f'Error: {str(e)}')
        return redirect('admin_users')

    users = User.objects.filter(is_staff=False).order_by('-date_joined')
    context = {'users': users, 'total_users': users.count()}
    return render(request, 'admins/users.html', context)

# ─── Admin investment plans (CREATE / EDIT / DELETE) ─────────────────────────────
@user_passes_test(is_admin)
def admin_plans(request):
    """Admin: manage investment plans – create, toggle active, delete"""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            try:
                name           = request.POST.get('name', '').strip().upper()
                roi            = Decimal(request.POST.get('roi_percentage', 0))
                duration       = int(request.POST.get('duration_days', 1))
                min_inv        = Decimal(request.POST.get('min_investment', 0))
                max_inv_raw    = request.POST.get('max_investment', '').strip()
                max_inv        = Decimal(max_inv_raw) if max_inv_raw else None
                referral_bonus = Decimal(request.POST.get('referral_bonus', 5))
                description    = request.POST.get('description', '').strip()
                capital_return = request.POST.get('capital_return') == 'on'

                if not name:
                    messages.error(request, 'Plan name is required.')
                    return redirect('admin_plans')
                if InvestmentTier.objects.filter(name=name).exists():
                    messages.error(request, f'A plan named "{name}" already exists.')
                    return redirect('admin_plans')

                InvestmentTier.objects.create(
                    name=name, roi_percentage=roi, duration_days=duration,
                    min_investment=min_inv, max_investment=max_inv,
                    referral_bonus=referral_bonus, incentive_description=description,
                    is_active=True, capital_return=capital_return
                )
                messages.success(request, f'Plan "{name}" created successfully!')
            except Exception as e:
                messages.error(request, f'Error creating plan: {e}')

        elif action == 'toggle':
            plan_id = request.POST.get('plan_id')
            plan = get_object_or_404(InvestmentTier, id=plan_id)
            plan.is_active = not plan.is_active
            plan.save()
            messages.success(request, f'Plan "{plan.name}" {"activated" if plan.is_active else "deactivated"}.')

        elif action == 'delete':
            plan_id = request.POST.get('plan_id')
            plan = get_object_or_404(InvestmentTier, id=plan_id)
            name = plan.name
            plan.delete()
            messages.success(request, f'Plan "{name}" deleted.')

        return redirect('admin_plans')

    plans = InvestmentTier.objects.all().order_by('min_investment')
    return render(request, 'admins/plans.html', {'plans': plans})

# ─── Password reset ───────────────────────────────────────────────────────────────
def forgot_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
            from django.contrib.auth.tokens import default_token_generator
            from django.utils.http import urlsafe_base64_encode
            from django.utils.encoding import force_bytes
            token = default_token_generator.make_token(user)
            uid   = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = request.build_absolute_uri(f'/reset-password/{uid}/{token}/')
            send_mail('Password Reset – AspenOptions', f'Reset link: {reset_link}', 'noreply@aspenoptions.org', [email], fail_silently=True)
        except User.DoesNotExist:
            pass
        return JsonResponse({'success': True})
    return JsonResponse({'success': False})

def reset_password(request, uidb64, token):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    try:
        uid  = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except Exception:
        user = None
    if user and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            np = request.POST.get('new_password')
            cp = request.POST.get('confirm_password')
            if np != cp:
                messages.error(request, 'Passwords do not match')
                return render(request, 'landing/reset_password.html', {'valid_link': True})
            if len(np) < 6:
                messages.error(request, 'Password must be at least 6 characters')
                return render(request, 'landing/reset_password.html', {'valid_link': True})
            user.set_password(np)
            user.save()
            messages.success(request, 'Password reset successful!')
            return redirect('signin')
        return render(request, 'landing/reset_password.html', {'valid_link': True})
    return render(request, 'landing/reset_password.html', {'valid_link': False})
