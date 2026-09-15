import json

from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.u_id = self.scope["url_route"]["kwargs"]["u_id"]
        self.group_name = f"notifications_{self.u_id}"

        print(f"🔌 WebSocket CONNECT: user={self.u_id}")

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name,
        )

        await self.accept()

        print(f"✅ WebSocket ACCEPTED: user={self.u_id}")

        await self.send(
            text_data=json.dumps({
                "type": "connection",
                "message": "WebSocket connected successfully",
                "u_id": self.u_id,
            })
        )

    async def disconnect(self, close_code):
        print(
            f"🔌 WebSocket DISCONNECTED: user={self.u_id}, code={close_code}"
        )
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name,
        )

    async def receive(self, text_data):
        print(f"📥 WebSocket received: {text_data}")
        try:
            data = json.loads(text_data)
            if data.get("type") == "ping":
                await self.send(
                    text_data=json.dumps({"type": "pong"})
                )
        except Exception as e:
            print(f"❌ WebSocket receive error: {e}")


    async def send_notification(self, event):
        print(f"📤 Sending notification to user={self.u_id}: {event}")

        # Forward only the inner data payload to Flutter
        await self.send(
            text_data=json.dumps(event["data"])
        )

    async def appointment_status_changed(self, event):
        print(f"📤 Sending status update to user={self.u_id}: {event}")

        # Forward only the inner data payload to Flutter
        await self.send(
            text_data=json.dumps(event["data"])
        )