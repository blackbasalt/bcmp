from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.generic import View


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
                                 'Введите логин')
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
    """Выход только POST-ом: ссылку на /logout/ может открыть чужая страница."""

    def post(self, request):
        logout(request)
        messages.add_message(request, messages.SUCCESS, 'Вы вышли из системы')
        return redirect('login')
