# Create your views here.
from django.http import HttpResponse
from django.shortcuts import render

from .models import Error

def index(request):
    errors = Error.objects.all().order_by("-last_event")
    return render(request, "centaur/index.html", { "errors": errors})

def error(request, error_id):
    error = get_object_or_404(Error, pk=error_id)

    return render(request, "centaur/error.html", { "error": error })