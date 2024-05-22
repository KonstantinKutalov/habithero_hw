from rest_framework import generics, permissions
from rest_framework.response import Response
from users.models import User, Token
from django.contrib.auth import authenticate
from .serializers import UserSerializer, RegisterSerializer, LoginSerializer
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework.generics import CreateAPIView


class RegisterView(CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Проверка уникальности
        try:
            User.objects.get(username=serializer.validated_data['username'])
            return Response({'error': 'Username already exists'}, status=400)
        except User.DoesNotExist:
            pass

        try:
            User.objects.get(email=serializer.validated_data['email'])
            return Response({'error': 'Email already exists'}, status=400)
        except User.DoesNotExist:
            pass

        try:
            User.objects.get(telegram_chat_id=serializer.validated_data['telegram_chat_id'])
            return Response({'error': 'Telegram chat ID already exists'}, status=400)
        except User.DoesNotExist:
            pass

        # Создание пользователя
        try:
            user = serializer.save()  # Создайте пользователя с помощью serializer.save()
            print(f'Создан пользователь с ID {user.id}')

            # Установите telegram_chat_id для пользователя
            user.telegram_chat_id = serializer.validated_data['telegram_chat_id']
            user.save()  # Сохраните изменения в user

            token, created = Token.objects.get_or_create(user=user)
            return Response({'token': token.key, 'id': user.id}, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({'error': str(e)}, status=400)
        except IntegrityError as e:
            return Response({'error': str(e)}, status=400)


class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(username=serializer.validated_data['username'],
                            password=serializer.validated_data['password'])
        if user is not None:
            token, created = Token.objects.get_or_create(user=user)
            return Response({'token': token.key})
        return Response({'error': 'Invalid Credentials'}, status=400)
