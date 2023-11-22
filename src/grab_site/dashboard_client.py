import os
import json
import asyncio
import websockets


class Decayer:
	def __init__(self, initial, multiplier, maximum):
		"""
		initial    - initial number to return
		multiplier - multiply number by this value after each call to decay()
		maximum    - cap number at this value
		"""
		self.initial = initial
		self.multiplier = multiplier
		self.maximum = maximum
		self.reset()

	def reset(self):
		# First call to .decay() will multiply, but we want to get the `intitial`
		# value on the first call to .decay(), so divide.
		self.current = self.initial / self.multiplier
		return self.current

	def decay(self):
		self.current = min(self.current * self.multiplier, self.maximum)
		return self.current


async def send_object(ws, obj):
	await ws.send(json.dumps(obj).encode("utf-8"))

async def sender(plugin, uri):
	decayer = Decayer(0.25, 1.5, 8)
	while True:
		try:
			async with websockets.connect(uri) as ws:
				print(f"Connected to {uri}")
				decayer.reset()
				await send_object(ws, {
					"type": "hello",
					"mode": "grabber",
					"url":  plugin.job_data["url"]
				})
				while True:
					obj = await plugin.ws_queue.get()
					try:
						await send_object(ws, obj)
					finally:
						plugin.ws_queue.task_done()
		except Exception as e:
			delay = decayer.decay()
			print(f"Disconnected from ws:// server: {repr(e)}")
			await asyncio.sleep(delay)
