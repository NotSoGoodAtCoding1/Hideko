"""Quick test for timer tool fix."""
from config import load_config
from response_handler import ResponseHandler
from tools.timer_tool import TimerTool
from tools.registry import ToolRegistry
from events import EventBus


class DummyScheduler:
    def __init__(self):
        self.jids = []
        
    def schedule(self, cb, delay):
        import uuid
        jid = uuid.uuid4().hex
        self.jids.append((jid, delay))
        print(f"  [DummyScheduler.schedule: jid={jid}, delay={delay}]")
        return jid


config = load_config()
bus = EventBus()
registry = ToolRegistry()

scheduler = DummyScheduler()
timer_tool = TimerTool(scheduler, bus, lambda x: print(f"  [queue_speech: {x}]"))
registry.register(timer_tool)

handler = ResponseHandler(config)
response = handler.respond("set a timer for 5 minutes")
print(f"Matched trigger: tool={response.tool_action}")

# Now execute with the full user text
result = registry.execute(
    "set_timer",
    text="set a timer for 5 minutes",
    response_text=response.text,
)
print(f"Result: ok={result.ok}, text='{result.text}'")
