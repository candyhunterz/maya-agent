import asyncio
import pytest
from maya_agent.core.frames import encode_frame, FrameDecoder
from maya_agent.core.protocol import (
    ToolInventoryMessage, UserIntentMessage, ToolCallMessage, parse_message,
)
from maya_agent.sidecar.maya_client import MayaClient


@pytest.mark.asyncio
async def test_round_trip_via_loopback():
    """Stand up a local TCP server, have MayaClient connect to it, exchange frames."""
    received: list[bytes] = []

    async def handle(reader, writer):
        # Read one frame: 4-byte length + body
        header = await reader.readexactly(4)
        length = int.from_bytes(header, "big")
        body = await reader.readexactly(length)
        received.append(body)
        # Send back an inventory message
        inv = ToolInventoryMessage(tools=[]).model_dump()
        writer.write(encode_frame(inv))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    serving = asyncio.create_task(server.serve_forever())

    client = MayaClient()
    await client.connect_tcp("127.0.0.1", port)

    # Send a user_intent
    await client.send(UserIntentMessage(intent_id="i1", text="hello"))

    # Receive the inventory back
    msg = await asyncio.wait_for(client.receive(), timeout=2.0)
    assert isinstance(msg, ToolInventoryMessage)

    server.close()
    serving.cancel()
    await client.close()
