import json

# Make sure we don't store session cookie data in the trace
COOKIE_BLACKLIST = (
    "sessionid",
    "SACSID"
)

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

    for name, value in request.COOKIES.items():
        if name in COOKIE_BLACKLIST:
            continue

        result["COOKIES"][name] = repr(value)

    for var in sorted(request.META.items()):
        result["META"][var[0]] = repr(var[1])

    return json.dumps(result)
