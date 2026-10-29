from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect, render


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome! Star currencies to build your watchlist.")
        return redirect("currency_list")
    return render(request, "registration/signup.html", {"form": form})
