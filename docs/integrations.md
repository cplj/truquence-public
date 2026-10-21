# Installed interfaces

The 0.3.0 candidate was exercised with Python 3.10 and 3.14 on macOS using synthetic inputs. Core and Recorder have no runtime dependencies. Install `truquence[mcp]` for the MCP stdio server; `truquence-mcp --help` works without that extra, but starting the server requires it. No agent product is listed as supported by these tests.

## MCP client example

Install the MCP extra in a virtual environment, then run:

```python
import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    parameters = StdioServerParameters(command="truquence-mcp")
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            contract = {"x-schema": "truquence.workflow-contract.v0.2",
                        "x-source": "make", "x-scope": "execution_observation",
                        "x-scenario_id": 1229, "x-execution_id": "run-1",
                        "x-expect_operations": 10}
            execution = {"id": "run-1", "imtId": "1632371744497_scenario.1229.auto.run-1",
                         "type": "auto", "status": 1, "operations": 10}
            result = await session.call_tool("truquence_accept", {
                "contract_json": json.dumps(contract),
                "execution_json": json.dumps(execution), "source": "make"})
            print(result)

asyncio.run(main())
```

The matching synthetic records return `status: PASS`, `accepted: true`, `gateBlocked: false`, `evidence_level: imported`. The nested report keeps `business_acceptance: UNKNOWN`. A mismatched operation count returns FAIL; an incomplete export returns UNKNOWN. Invalid JSON is a tool error. This checks supplied bytes without following paths or URLs, accessing remote services, or running workflows.

The server exposes one tool: `truquence_accept`. Its input schema is available through MCP `tools/list`. Workflow input/output fields are documented in [workflow contracts](workflows.md); action-contract schemas remain in [contracts](contracts.md). MCP has no receipt signing, private rule engine, or consensus functionality.

## Evidence levels

- Passive capture: a hook collects a local event. Collection is bounded by hook delivery and local persistence; missing events cannot be inferred from the ledger.
- Self reported: Recorder rows use `evidence_level: self_reported` because tool names, arguments and result codes come from the event producer. Synthetic stdin can produce the same shape. Hook collection does not authenticate that producer.
- Imported: MCP accepts supplied workflow exports. No independent observer checks the external action.

Receipt verification checks the chain currently present. A writer can recompute the chain or remove a valid suffix. Authenticity and completeness stay UNKNOWN. Redaction is best effort; inspect ledgers before sharing. Recorder integration tests used isolated synthetic settings; real host hooks, performance, crash durability and agent product integration remain untested. Windows Recorder support is untested and POSIX APIs are required.
