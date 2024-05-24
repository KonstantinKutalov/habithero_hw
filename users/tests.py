from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from users.models import User


class RegistrationAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.registration_url = reverse('register')

    def test_successful_registration(self):
        data = {
            'username': 'testuser',
            'email': 'testuser@example.com',
            'password': 'testpassword',
            'telegram_chat_id': '1234567890',
        }
        response = self.client.post(self.registration_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('token', response.data)
        self.assertIn('id', response.data)

    def test_registration_with_existing_username(self):
        User.objects.create_user(username='existinguser', email='existinguser@example.com', password='testpassword')
        data = {
            'username': 'existinguser',
            'email': 'testuser2@example.com',
            'password': 'testpassword',
            'telegram_chat_id': '1234567890',
        }
        response = self.client.post(self.registration_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)
        self.assertEqual(response.data['username'][0], 'user with this username already exists.')

    def test_registration_with_existing_email(self):
        User.objects.create_user(username='testuser2', email='existingemail@example.com', password='testpassword')
        data = {
            'username': 'testuser3',
            'email': 'existingemail@example.com',
            'password': 'testpassword',
            'telegram_chat_id': '1234567890',
        }
        response = self.client.post(self.registration_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertEqual(response.data['email'][0], 'user with this email already exists.')

    def test_registration_with_existing_telegram_id(self):
        User.objects.create_user(username='testuser4', email='testuser4@example.com', password='testpassword',
                                 telegram_chat_id='1234567890')
        data = {
            'username': 'testuser5',
            'email': 'testuser5@example.com',
            'password': 'testpassword',
            'telegram_chat_id': '1234567890',
        }
        response = self.client.post(self.registration_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('telegram_chat_id', response.data)
        self.assertEqual(response.data['telegram_chat_id'][0], 'user with this telegram chat id already exists.')


class LoginAPITestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse('login')
        self.user = User.objects.create_user(username='testuser', email='testuser@example.com', password='testpassword')

    def test_successful_login(self):
        data = {
            'username': 'testuser',
            'password': 'testpassword',
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('token', response.data)

    def test_login_with_invalid_credentials(self):
        data = {
            'username': 'testuser',
            'password': 'wrongpassword',
        }
        response = self.client.post(self.login_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Invalid Credentials')
