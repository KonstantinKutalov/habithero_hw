from rest_framework import serializers
from .models import Habit
from rest_framework.serializers import CurrentUserDefault
from users.models import User


class HabitSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=CurrentUserDefault())

    class Meta:
        model = Habit
        fields = '__all__'
