from google.appengine.ext.deferred import defer

from .models import Event

class CentaurMiddleware(object):

    def process_response(self, request, response):
        if response.status_code > 400 and not getattr(request, "_exception_logged", False):
            Event.log_event(request, response=response)
        return response

    def process_exception(self, request, exception):
        Event.log_event(request, exception=exception)
        request._exception_logged = True