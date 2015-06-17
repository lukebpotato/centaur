import json
from django.http import SimpleCookie

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

    whitelisted_cookie = SimpleCookie()
    for name, value in request.COOKIES.items():
        if name in COOKIE_BLACKLIST:
            continue

        whitelisted_cookie[name] = value
        result["COOKIES"][name] = repr(value)

    for meta_name, meta_value in sorted(request.META.items()):
        if meta_name == 'HTTP_COOKIE':
            meta_value = whitelisted_cookie.output(header='', sep='; ')
        result["META"][meta_name] = repr(meta_value)

    return json.dumps(result)
