import asyncio
class EventBus:
    def __init__(self):self.subscribers=set()
    async def publish(self,event):
        dead=[]
        for q in list(self.subscribers):
            try:q.put_nowait(event)
            except asyncio.QueueFull:dead.append(q)
        for q in dead:self.subscribers.discard(q)
    def subscribe(self):
        q=asyncio.Queue(maxsize=500);self.subscribers.add(q);return q
    def unsubscribe(self,q):self.subscribers.discard(q)
