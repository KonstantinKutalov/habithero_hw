from rest_framework.test import APITestCase
from django.urls import reverse
from rest_framework import status
from users.models import User
from habits.models import Habit
from rest_framework.authtoken.models import Token


class HabitTests(APITestCase):
    def setUp(self):
        # Создание тестового пользователя
        self.test_user = User.objects.create_user(
            username='testuser',
            password='testpassword',
            email='testuser@example.com'
        )
        self.token, _ = Token.objects.get_or_create(user=self.test_user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key)

        # Создание тестовой привычки
        self.test_habit = Habit.objects.create(
            user=self.test_user,
            name='Test Habit',
            place='Home',
            time='10:00:00',
            action='Do something',
            is_pleasant=False,
            frequency=1,
            reward='Reward',
            execution_time=30,
            is_public=False
        )

    def test_create_habit(self):
        """Тестирование создания привычки."""
        url = reverse('habit-list')
        data = {
            'name': 'New Habit',
            'place': 'Office',
            'time': '09:00:00',
            'action': 'Do another thing',
            'is_pleasant': True,
            'frequency': 2,
            'reward': '',
            'execution_time': 45,
            'is_public': True
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Habit.objects.count(), 2)
        self.assertEqual(Habit.objects.last().name, 'New Habit')

    def test_list_habits(self):
        """Тестирование списка привычек пользователя."""
        url = reverse('habit-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_retrieve_habit(self):
        """Тестирование получения одной привычки."""
        url = reverse('habit-detail', args=[self.test_habit.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Test Habit')

    def test_update_habit(self):
        """Тестирование обновления привычки."""
        url = reverse('habit-detail', args=[self.test_habit.id])
        data = {
            'name': 'Updated Habit',
            'place': 'Work',
        }
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Habit.objects.get(id=self.test_habit.id).name, 'Updated Habit')

    def test_delete_habit(self):
        """Тестирование удаления привычки."""
        url = reverse('habit-detail', args=[self.test_habit.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Habit.objects.count(), 0)

    def test_public_habits(self):
        """Тестирование списка публичных привычек."""
        url = reverse('public-habit-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_validate_reward_and_linked_habit(self):
        habit = Habit(
            user=self.user,
            name="Test Habit",
            place="Home",
            time="10:00",
            action="Do something",
            reward="Reward",
            linked_habit=Habit.objects.create(
                user=self.user,
                name="Linked Habit",
                place="Office",
                time="12:00",
                action="Do other thing",
                is_pleasant=True
            )
        )
        with self.assertRaises(ValidationError) as context:
            habit.full_clean()
        self.assertEqual(context.msg, ["Вы не можете установить и награду, и связанную привычку."])