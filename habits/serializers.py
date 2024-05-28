from rest_framework import serializers
from .models import Habit
from rest_framework.serializers import CurrentUserDefault
from users.models import User


class HabitSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=CurrentUserDefault())

    def validate_execution_time(self, value):
        if value > 120:
            raise serializers.ValidationError("Время выполнения не может превышать 120 секунд.")
        return value

    def validate_frequency(self, value):
        if value > 7:
            raise serializers.ValidationError("Вы не можете выполнять привычку реже, чем раз в 7 дней.")
        return value

    def validate(self, data):
        # Валидация связанной привычки и вознаграждения
        if data.get('reward') and data.get('linked_habit'):
            raise serializers.ValidationError("Вы не можете установить и награду, и связанную привычку.")

        # Валидация приятных привычек
        if data.get('is_pleasant') and (data.get('reward') or data.get('linked_habit')):
            raise serializers.ValidationError("Приятные привычки не могут иметь награды или связанных привычек.")

        # Валидация связанной привычки на приятность
        linked_habit = data.get('linked_habit')
        if linked_habit and not linked_habit.is_pleasant:
            raise serializers.ValidationError("Связанная привычка должна быть приятной.")

        return data

    class Meta:
        model = Habit
        fields = '__all__'
