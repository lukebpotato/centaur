from .models import Event

class CentaurMiddleware(object):

    def process_response(self, request, response):
        if response.status_code > 400 and not getattr(request, "_exception_logged", False):
            event = Event.log_event(request, response=response)
            request.centaur_event = event
        return response

    def process_exception(self, request, exception):
        event = Event.log_event(request, exception=exception)
        request.centaur_event = event
        request._exception_logged = True
