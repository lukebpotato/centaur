import json

def construct_request_json(request):
    result = {
        "GET": {},
        "POST": {},
        "FILES": {},
        "META": {},
        "COOKIES": {}
    }

    for var in request.GET.items():
        result["GET"][var[0]] = repr(var[1])

    for var in request.POST.items():
        result["POST"][var[0]] = repr(var[1])

    for var in request.FILES.items():
        result["FILES"][var[0]] = repr(var[1])

    for var in request.COOKIES.items():
        result["COOKIES"][var[0]] = repr(var[1])

    for var in sorted(request.META.items()):
        result["META"][var[0]] = repr(var[1])

    return json.dumps(result)
