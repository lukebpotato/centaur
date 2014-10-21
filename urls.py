
from django.conf.urls import url
from centaur import views

urlpatterns = [
    url(r'^$', views.index, name='centaur_index'),
    url(r'^error/(?P<error_id>\d+)/$', views.error, name="centaur_error"),
    url(r'^clear/$', views.clear_old_events, name="centaur_clear_cron"),
]
