from django.urls import path
from .views import SignUpView, PhoneLoginView, ChatBotAPIView, SendEmailOTPView, VerifyEmailOTPView, SendOTPView

urlpatterns = [
    path('signup/', SignUpView.as_view(), name='signup'),
    path('login/', PhoneLoginView.as_view(), name='login'),
    path('send_otp/', SendOTPView.as_view(), name='send_otp'),
    path('send_email_otp/', SendEmailOTPView.as_view(), name='send_email_otp'),
    path('verify_email_otp/', VerifyEmailOTPView.as_view(), name='verify_email_otp'),
    path('chat/', ChatBotAPIView.as_view(), name='chatbot-api'),
]
