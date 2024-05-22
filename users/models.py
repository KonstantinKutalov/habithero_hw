import secrets

from django.db import models
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import BaseUserManager
from keyring.testing.util import ALPHABET
from rest_framework.authtoken.models import Token
from django.dispatch import receiver
from django.db.models.signals import post_save


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, telegram_chat_id=None, **extra_fields):
        if not email:
            raise ValueError('Email должен быть указан')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, telegram_chat_id=telegram_chat_id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser должен иметь is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser должен иметь is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


class User(models.Model):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    telegram_chat_id = models.CharField(max_length=255, blank=True, null=True, unique=True)

    objects = UserManager()

    REQUIRED_FIELDS = ('email',)
    USERNAME_FIELD = ('username')

    is_anonymous = False
    is_authenticated = True

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def __str__(self):
        return self.email

    def create_user(self, username, email, password, telegram_chat_id=None):
        user = self.model(
            username=username,
            email=email,
            password=make_password(password),  # Шифрование пароля
            telegram_chat_id=telegram_chat_id
        )
        user.save(using=self._db)
        return user


class Token(models.Model):
    key = models.CharField(max_length=40, primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        super().save(*args, **kwargs)

    def generate_key(self):
        return ''.join(secrets.choice(ALPHABET) for i in range(40))


@receiver(post_save, sender=User)


def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)



# groups = models.ManyToManyField(
#     'auth.Group',
#     verbose_name='groups',
#     blank=True,
#     help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
#     related_name='custom_user_set',
# )
# user_permissions = models.ManyToManyField(
#     'auth.Permission',
#     verbose_name='user permissions',
#     blank=True,
#     help_text='Specific permissions for this user.',
#     related_name='custom_user_set',
# )
