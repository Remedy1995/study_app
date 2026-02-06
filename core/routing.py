from django.urls import re_path
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from core import consumer

websocket_urlpatterns = [
    re_path(r"ws/lecture/(?P<lecture_id>\d+)/$", consumer.LectureConsumer.as_asgi()),
]


