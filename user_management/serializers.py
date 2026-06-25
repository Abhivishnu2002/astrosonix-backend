from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile



class SignUpSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(
        max_length=10,
        min_length=10,
        error_messages={
            'min_length': 'Phone number must be exactly 10 digits.',
            'max_length': 'Phone number must be exactly 10 digits.',
            'blank': 'Phone number is required.',
        }
    )
    full_name = serializers.CharField()
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = User
        fields = ['phone_number', 'full_name', 'email']

    def validate_phone_number(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("Phone number must contain only digits.")
        
        if UserProfile.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")

        return value
    
    def create(self, validated_data):
        phone = validated_data.pop('phone_number')
        name = validated_data.pop('full_name')
        email = validated_data.pop('email', None)
        username = phone

        # Create user
        user = User.objects.create_user(username=username, first_name=name, email=email or '')

        # Create user profile
        UserProfile.objects.create(user=user, phone_number=phone, full_name=name, email=email)

        return user



class PhoneLoginSerializer(serializers.Serializer):
    phone_number = serializers.CharField(required=False)
    identifier = serializers.CharField(required=False)

    def validate(self, attrs):
        if not attrs.get('phone_number') and not attrs.get('identifier'):
            raise serializers.ValidationError("Either phone_number or identifier is required.")
        return attrs
