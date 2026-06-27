from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Landing pages
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('faq/', views.faq, name='faq'),
    path('packages/', views.package, name='packages'),
    path('privacy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('contact/', views.contact, name='contact'),

    # Authentication
    path('signin/', views.signin, name='signin'),
    path('signup/', views.signup, name='signup'),
    path('signout/', views.user_logout, name='signout'),

    # User dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('deposit/', views.deposit, name='deposit'),
    path('withdraw/', views.withdraw, name='withdraw'),
    path('history/', views.history, name='history'),
    path('profile/', views.profile, name='profile'),
    path('investments/', views.investments, name='investments'),

    # AJAX
    path('api/wallet-address/', views.get_wallet_address, name='get_wallet_address'),

    # Admin panel
    path('admin_dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin_deposits/', views.admin_deposits, name='admin_deposits'),
    path('admin_investments/', views.admin_investments, name='admin_investments'),
    path('admin_settings/', views.admin_settings, name='admin_settings'),
    path('admin_withdrawals/', views.admin_withdrawals, name='admin_withdrawals'),
    path('admin_users/', views.admin_users, name='admin_users'),
    path('admin_plans/', views.admin_plans, name='admin_plans'),
    path('admins/add-funds/', views.add_funds, name='add_funds'),

    # Password reset
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<uidb64>/<token>/', views.reset_password, name='reset_password'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
