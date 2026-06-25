import os
import random
import requests
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User
from .serializers import SignUpSerializer, PhoneLoginSerializer
from .models import UserProfile, EmailOTP, PhoneOTP
from rest_framework.authtoken.models import Token

# --- Message Central Helpers ---

def get_message_central_token():
    customer_id = getattr(settings, "MESSAGE_CENTRAL_CUSTOMER_ID", "")
    key = getattr(settings, "MESSAGE_CENTRAL_KEY", "")
    email = getattr(settings, "MESSAGE_CENTRAL_EMAIL", "")
    
    if not customer_id or not key or "your_customer_id" in customer_id or "your_base64_encoded" in key:
        return None
        
    # If the key is already a JWT token, return it directly
    if key.startswith("eyJ") and "." in key:
        return key
        
    url = "https://cpaas.messagecentral.com/auth/v1/authentication/token"
    params = {
        "customerId": customer_id,
        "key": key,
        "scope": "NEW",
        "country": "91"
    }
    if email and "your_message_central" not in email:
        params["email"] = email
        
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json().get("token")
    except Exception as e:
        print(f"Error fetching Message Central token: {e}")
    return None


def send_message_central_otp(phone_number):
    token = get_message_central_token()
    if not token:
        # Generate random OTP locally and return it as the mock verification_id
        mock_otp = f"{random.randint(100000, 999999)}"
        return f"MOCK_{mock_otp}", None
        
    clean_phone = phone_number.replace("+91", "").replace("+", "").strip()
    
    url = "https://cpaas.messagecentral.com/verification/v3/send"
    params = {
        "countryCode": "91",
        "flowType": getattr(settings, "MESSAGE_CENTRAL_FLOW_TYPE", "SMS"),
        "mobileNumber": clean_phone
    }
    headers = {
        "authToken": token,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, params=params, headers=headers, timeout=10)
        res_data = response.json()
        if response.status_code == 200 and res_data.get("message") == "SUCCESS":
            verification_id = res_data.get("data", {}).get("verificationId")
            return verification_id, None
        else:
            error_msg = res_data.get("message") or "Failed to send OTP via Message Central"
            return None, error_msg
    except Exception as e:
        return None, str(e)


def validate_message_central_otp(phone_number, verification_id, code):
    if not verification_id:
        return False
        
    if verification_id.startswith("MOCK_"):
        local_code = verification_id.replace("MOCK_", "")
        return local_code == code
        
    token = get_message_central_token()
    if not token:
        return False
        
    url = "https://cpaas.messagecentral.com/verification/v3/validateOtp"
    params = {
        "verificationId": verification_id,
        "code": code
    }
    headers = {
        "authToken": token
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        res_data = response.json()
        print(f"\n[OTP VALIDATION LOG] URL: {url} | Status Code: {response.status_code} | Response Text: {response.text}\n", flush=True)
        if response.status_code == 200:
            resp_code = res_data.get("responseCode")
            msg = res_data.get("message", "")
            if resp_code == 200 or resp_code == "200" or msg in ["SUCCESS", "Success", "VERIFICATION_COMPLETED"]:
                return True
    except Exception as e:
        print(f"Error validating OTP: {e}", flush=True)
    return False



# --- API Views ---

class SendOTPView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        phone_number = request.data.get("phone_number", "").strip()
        is_login = request.data.get("is_login", False)
        
        if not phone_number:
            return Response({"error": "Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        # Standardize formatting to 10 digits
        clean_phone = phone_number.replace("+91", "").replace("+", "").strip()
        if len(clean_phone) != 10 or not clean_phone.isdigit():
            return Response({"error": "Please enter a valid 10-digit phone number"}, status=status.HTTP_400_BAD_REQUEST)
            
        # If it is login, check if user is registered
        if is_login:
            exists = UserProfile.objects.filter(phone_number=clean_phone).exists()
            if not exists:
                exists = User.objects.filter(username=clean_phone).exists()
            if not exists:
                return Response({"error": "Phone number not found or not registered."}, status=status.HTTP_404_NOT_FOUND)
                
        verification_id, error = send_message_central_otp(clean_phone)
        if error:
            return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
            
        # Store verification record
        PhoneOTP.objects.update_or_create(
            phone_number=clean_phone,
            defaults={"verification_id": verification_id}
        )
        
        # If mock mode, log it in terminal console
        if verification_id.startswith("MOCK_"):
            otp = verification_id.replace("MOCK_", "")
            print(f"\n========================================\n[LOCAL SMS SERVICE] Phone: {clean_phone} | OTP: {otp}\n========================================\n")
            
        return Response({"message": "OTP sent successfully"})


class SignUpView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
        otp = request.data.get("otp", "").strip()
        phone_number = request.data.get("phone_number", "").strip()
        
        if not otp or not phone_number:
            return Response({"error": "Phone number and OTP code are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        clean_phone = phone_number.replace("+91", "").replace("+", "").strip()
        
        # Validate SignUp Form first
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        # Retrieve verification ID
        try:
            record = PhoneOTP.objects.get(phone_number=clean_phone)
        except PhoneOTP.DoesNotExist:
            return Response({"error": "OTP transaction not found. Please request OTP first."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Verify OTP code
        is_valid = validate_message_central_otp(clean_phone, record.verification_id, otp)
        if not is_valid:
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Complete SignUp
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)
        
        # Clear OTP transaction
        record.delete()
        
        # Get full name from profile
        full_name = ""
        try:
            full_name = user.profile.full_name
        except Exception:
            full_name = user.first_name or user.username
        
        return Response({
            "message": "User created successfully",
            "token": token.key,
            "full_name": full_name
        }, status=status.HTTP_201_CREATED)
        
    def get(self, request):
        users = User.objects.all()
        user_list = [{"id": u.id, "username": u.username, "email": u.email} for u in users]
        return Response({"users": user_list}, status=200)


class PhoneLoginView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        phone = request.data.get("identifier", "").strip()
        otp = request.data.get("otp", "").strip()
        
        if not phone or not otp:
            return Response({"error": "Phone number and OTP code are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        clean_phone = phone.replace("+91", "").replace("+", "").strip()
        
        # Retrieve verification ID
        try:
            record = PhoneOTP.objects.get(phone_number=clean_phone)
        except PhoneOTP.DoesNotExist:
            return Response({"error": "OTP transaction not found. Please request OTP first."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Verify OTP
        is_valid = validate_message_central_otp(clean_phone, record.verification_id, otp)
        if not is_valid:
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
            
        # Authenticate User
        try:
            user_profile = UserProfile.objects.get(phone_number=clean_phone)
            user = user_profile.user
        except UserProfile.DoesNotExist:
            try:
                user = User.objects.get(username=clean_phone)
            except User.DoesNotExist:
                return Response({"error": "User profile not found"}, status=status.HTTP_404_NOT_FOUND)
                
        token, created = Token.objects.get_or_create(user=user)
        
        # Clear OTP transaction
        record.delete()
        
        # Get full name from profile
        full_name = ""
        try:
            full_name = user.profile.full_name
        except Exception:
            full_name = user.first_name or user.username
        
        return Response({
            "message": "Login success",
            "user_id": user.id,
            "token": token.key,
            "full_name": full_name
        }, status=status.HTTP_200_OK)


class SendEmailOTPView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get("email", "").strip()
        if not email:
            return Response({"message": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        otp = f"{random.randint(100000, 999999)}"
        
        EmailOTP.objects.update_or_create(
            email=email,
            defaults={"otp": otp}
        )
        
        print(f"\n========================================\n[LOCAL EMAIL SERVICE] Email: {email} | OTP: {otp}\n========================================\n")
        
        return Response({"message": "OTP sent successfully"})


class VerifyEmailOTPView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        email = request.data.get("email", "").strip()
        otp = request.data.get("otp", "").strip()
        if not email or not otp:
            return Response({"message": "Email and OTP are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            otp_obj = EmailOTP.objects.get(email=email, otp=otp)
            
            try:
                user_profile = UserProfile.objects.get(email=email)
                user = user_profile.user
            except UserProfile.DoesNotExist:
                user = User.objects.filter(email=email).first()
                if not user:
                    username = email.split('@')[0] + "_" + str(random.randint(1000, 9999))
                    user = User.objects.create_user(username=username, email=email)
                    UserProfile.objects.create(user=user, email=email, phone_number="", full_name=username)
                    
            token, created = Token.objects.get_or_create(user=user)
            otp_obj.delete()
            
            # Get full name from profile
            full_name = ""
            try:
                full_name = user.profile.full_name
            except Exception:
                full_name = user.first_name or user.username
            
            return Response({
                "message": "Login success",
                "user_id": user.id,
                "token": token.key,
                "full_name": full_name
            }, status=200)
            
        except EmailOTP.DoesNotExist:
            return Response({"message": "Invalid OTP or Email"}, status=status.HTTP_400_BAD_REQUEST)


class ChatBotAPIView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        messages = request.data.get("messages", [])
        if not messages:
            single_message = request.data.get("message", "").strip()
            if not single_message:
                return Response({"error": "Messages or message field is required."}, status=status.HTTP_400_BAD_REQUEST)
            messages = [{"role": "user", "content": single_message}]
        
        api_key = getattr(settings, "GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))
        if not api_key:
            return Response({"error": "Groq API key not configured on server."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        model = request.data.get("model", "llama-3.3-70b-versatile")
        temperature = request.data.get("temperature", 0.7)
        max_tokens = request.data.get("max_tokens", 300)
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30
            )
            response_data = response.json()
            if response.status_code != 200:
                error_msg = response_data.get("error", {}).get("message", "Groq API call failed")
                return Response({"error": error_msg}, status=response.status_code)
                
            reply = response_data["choices"][0]["message"]["content"]
            return Response({"response": reply}, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)