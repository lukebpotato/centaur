from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .models import Error


def index(request):
    errors = Error.objects.all().order_by("-last_event")
    return render(request, "centaur/index.html", { "errors": errors})

def error(request, error_id):
    error = get_object_or_404(Error, pk=error_id)

    page = request.GET.get('page', 0)
    paginator = Paginator(error.events.order_by('-created'), 1)
    try:
        events = paginator.page(page)
    except PageNotAnInteger:
        events = paginator.page(1)
    except EmptyPage:
        events = paginator.page(paginator.num_pages)

    return render(request, "centaur/error.html", { "error": error, "events": events })