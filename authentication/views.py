from django.conf import settings
from django.views import generic
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse_lazy
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.views.generic import View
from django.contrib import messages

# Create your views here.
class LoginView(View):
    def get(self, request):
        return render(request, 'auth/login.html')

    def post(self, request):
        context = {
            'data': request.POST,
            'has_error': False
        }
        username = request.POST.get('username')
        password = request.POST.get('password')
        if username == '':
            messages.add_message(request, messages.ERROR,
                                 'Введите email')
            context['has_error'] = True
        if password == '':
            messages.add_message(request, messages.ERROR,
                                 'Введите пароль')
            context['has_error'] = True
        user = authenticate(request, username=username, password=password)

        if not user and not context['has_error']:
            messages.add_message(request, messages.ERROR, 'Неверный логин или пароль')
            context['has_error'] = True

        if context['has_error']:
            return render(request, 'auth/login.html', status=401, context=context)
        login(request, user)
        return redirect(settings.LOGIN_REDIRECT_URL)

class LogoutView(View):
    def get(self, request):
        logout(request)
        messages.add_message(request, messages.SUCCESS, 'Успешно разлогинились')
        return redirect('login')
