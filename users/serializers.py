from rest_framework import serializers
from users.models import User
from django.contrib.auth.hashers import make_password


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'telegram_chat_id')

    def create(self, validated_data):
        # Удаляем "password" из validated_data, чтобы избежать ошибки:
        password = validated_data.pop('password')
        user = User(**validated_data)  # Создайте пользователя без пароля
        user.password = make_password(password)  # Установите пароль
        user.save()
        return user


class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'telegram_chat_id')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        # Проверьте, что validated_data содержит telegram_chat_id
        print(f'validated_data: {validated_data}')
        user = User.objects.create_user(
            validated_data['username'],
            validated_data['email'],
            validated_data['password'],
            validated_data.get('telegram_chat_id')
        )
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
