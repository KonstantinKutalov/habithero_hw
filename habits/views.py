from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import Habit
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from rest_framework import generics
from .serializers import HabitSerializer
from rest_framework.viewsets import ModelViewSet


class PublicHabitList(generics.ListAPIView):
    serializer_class = HabitSerializer
    pagination_class = PageNumberPagination  # пагинация

    def get_queryset(self):
        return Habit.objects.filter(is_public=True)


# class HabitViewSet(ModelViewSet):
#     queryset = Habit.objects.all()
#     serializer_class = HabitSerializer
#     pagination_class = HabitPagination

class HabitViewSet(viewsets.ModelViewSet):
    serializer_class = HabitSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination  # пагинация

    def get_queryset(self):
        print(f"User: {self.request.user}")
        if self.request.user.is_authenticated:
            return Habit.objects.filter(user=self.request.user)
        else:
            return Habit.objects.none()

    def create(self, request, *args, **kwargs):
        print(f"User: {self.request.user}")  # Проверка пользователя
        print(f"Auth Header: {self.request.META.get('HTTP_AUTHORIZATION')}")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=self.request.user)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class HabitPagination(PageNumberPagination):
    page_size = 5
    page_size_query_param = 'page_size'
    max_page_size = 100
