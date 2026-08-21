from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.forms import ProfileForm
from accounts.models import Profile


@login_required
def edit_profile(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Nutrition goals updated.")
            return redirect("edit-profile")
    else:
        form = ProfileForm(instance=profile)

    return render(request, "accounts/profile_form.html", {"form": form})
