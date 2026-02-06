import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

logger = logging.getLogger(__name__)

class LectureConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.lecture_id = self.scope["url_route"]["kwargs"].get("lecture_id")
            if not self.lecture_id:
                logger.warning("Connection rejected: Missing lecture_id in URL.")
                await self.close(code=4001)
                return

            self.group_name = f"lecture_{self.lecture_id}"

            # Add user info for potential auditing
            user = self.scope.get("user")
            logger.info(f"User {user if user.is_authenticated else 'Anonymous'} connected to {self.group_name} at {timezone.now()}.")

            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

        except Exception as e:
            logger.error(f"WebSocket connection failed: {str(e)}", exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"Disconnected from {self.group_name} with code {close_code}.")
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}", exc_info=True)

    async def receive(self, text_data=None, bytes_data=None):
        """
        Handles incoming WebSocket messages.
        """
        try:
            if not text_data:
                return

            data = json.loads(text_data)
            event = data.get("event")
            payload = data.get("data")

            if not event:
                await self.send_error("Missing 'event' field in message.")
                return

            # Echo message to group for now (can be customized)
            await self.channel_layer.group_send(
                self.group_name,
                {"type": "send_event", "event": event, "data": payload}
            )

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format.")
        except Exception as e:
            logger.error(f"Error in receive(): {str(e)}", exc_info=True)
            await self.send_error("Internal server error.")

    async def send_event(self, event):
        """
        Sends events to the client — called when a group message is received.
        """
        try:
            await self.send(text_data=json.dumps({
                "event": event.get("event"),
                "data": event.get("data"),
            }))
        except Exception as e:
            logger.error(f"Error sending event: {str(e)}", exc_info=True)

    async def send_error(self, message):
        """
        Helper function to send structured error messages.
        """
        await self.send(text_data=json.dumps({
            "event": "error",
            "data": {"message": message}
        }))
