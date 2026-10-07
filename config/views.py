from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render


# Staff only: the manual documents internal tables, operations queries and known gaps.
@staff_member_required
def manual(request):
    return render(request, "docs/manual.html")
