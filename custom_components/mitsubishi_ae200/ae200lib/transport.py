"""WebSocket transport for AE-200 controllers."""

import asyncio

import websockets
from websockets.extensions import permessage_deflate


async def ws_request(host: str, xml_payload: str, timeout: float = 10.0) -> str:
    """Send an XML request over WebSocket and return the raw response string.

    Opens a new connection per request — the AE-200 firmware is unreliable
    with long-lived connections.
    """
    uri = f"ws://{host}/b_xmlproc/"
    async with websockets.connect(
        uri,
        extensions=[permessage_deflate.ClientPerMessageDeflateFactory()],
        origin=f"http://{host}",
        subprotocols=["b_xmlproc"],
    ) as ws:
        await ws.send(xml_payload)
        response = await asyncio.wait_for(ws.recv(), timeout=timeout)
        await ws.close()
        return response
