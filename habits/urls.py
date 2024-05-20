from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import  PublicHabitList, HabitViewSet

router = DefaultRouter()
router.register(r'habits', HabitViewSet, basename='habit')

urlpatterns = [
    path('', include(router.urls)),
    path('public_habits/', PublicHabitList.as_view(), name='public-habit-list'),
]