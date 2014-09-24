import logging

from .models import Event

class CentaurMiddleware(object):

    def process_response(self, request, response):
        #We log errors when the status code is greater than 400, but not 408 which is the status code
        #used by deferred tasks when they (explicitly) retry. This isn't an error, and causes contention.
        if response.status_code > 400 and response.status_code != 408 and not getattr(request, "_exception_logged", False):
            try:
                event = Event.log_event(request, response=response)
                request.centaur_event = event
            except:
                #Same as below, ignore errors while logging to centaur
                logging.exception("Unable to log the error to centaur")

        return response

    def process_exception(self, request, exception):
        try:
            event = Event.log_event(request, exception=exception)
            request.centaur_event = event
            request._exception_logged = True
        except:
            logging.exception("Unable to log the error to centaur")
            return None #Explictly return None so the standard Django behaviour continues
