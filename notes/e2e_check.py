import asyncio, json, types
from unittest import mock
from mcpizza import server
from mcpizza.services import order_service
from mcpizza.api.client import api_client

async def main():
    tools = {t.name: t for t in await server.list_tools()}
    print("prepare_order listed:", "prepare_order" in tools)
    print("place_order props:", list(tools["place_order"].inputSchema["properties"]))
    order = types.SimpleNamespace(store=types.SimpleNamespace(id="7285"),
        customer=types.SimpleNamespace(first_name="A",last_name="B",email="a@b.co",phone="8435550100"),
        data={"Products":[{"Code":"14SCREEN","Qty":1}],"Coupons":[],"Address":{"Street":"x"},"Amounts":{},"ServiceMethod":"Delivery"})
    order_service.current_order = order
    with mock.patch.object(api_client,"price_order",return_value={"Status":1,"Order":{"Amounts":{"Customer":21.07}}}):
        r = await server.call_tool("prepare_order", {})
        txt = r[0].text; print(txt[:400])
        tok = [l.split(": ",1)[1] for l in txt.splitlines() if "Confirm Token" in l][0].strip()
        r2 = await server.call_tool("place_order", {"confirm_token": tok})
        print(r2[0].text[:300])
        r3 = await server.call_tool("place_order", {"confirm_token": tok})
        print("reuse:", r3[0].text[:120])
asyncio.run(main())
