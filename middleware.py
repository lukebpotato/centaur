from .models import Event

class CentaurMiddleware(object):

    def process_response(self, request, response):
        #We log errors when the status code is greater than 400, but not 408 which is the status code
        #used by deferred tasks when they (explicitly) retry. This isn't an error, and causes contention.
        if response.status_code > 400 and response.status_code != 408 and not getattr(request, "_exception_logged", False):
            event = Event.log_event(request, response=response)
            request.centaur_event = event
        return response

    def process_exception(self, request, exception):
        event = Event.log_event(request, exception=exception)
        request.centaur_event = event
        request._exception_logged = True
