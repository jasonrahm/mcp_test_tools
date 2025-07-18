#!/usr/bin/env python3
"""
Multi-Server MCP Client
Can connect to and manage multiple MCP servers simultaneously
Now with proper SSE support and better argument handling
"""

import asyncio
import json
import logging
import sys
from typing import Dict, Any, Optional, List
import argparse

import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPConnection:
    """Represents a single MCP server connection"""

    def __init__(self, name: str, server_url: str, transport: str = "websocket"):
        self.name = name
        self.server_url = server_url
        self.transport = transport
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.message_id = 0
        self.connected = False
        self.capabilities = {}

        # SSE-specific attributes
        self.sse_responses: Dict[int, asyncio.Future] = {}
        self.sse_task: Optional[asyncio.Task] = None
        self.client_id: Optional[str] = None

    async def connect(self):
        """Connect to MCP server"""
        self.session = aiohttp.ClientSession()

        if self.transport == "websocket":
            await self._connect_websocket()
        elif self.transport == "sse":
            await self._connect_sse()
        else:
            raise ValueError(f"Unknown transport: {self.transport}")

    async def _connect_websocket(self):
        """Connect via WebSocket"""
        ws_url = f"ws://{self.server_url}/ws"
        logger.info(f"[{self.name}] Connecting to WebSocket: {ws_url}")

        try:
            self.ws = await self.session.ws_connect(ws_url)
            self.connected = True
            logger.info(f"[{self.name}] WebSocket connected")
        except Exception as e:
            logger.error(f"[{self.name}] Failed to connect: {e}")
            self.connected = False
            raise

    async def _connect_sse(self):
        """Connect via SSE"""
        sse_url = f"http://{self.server_url}/sse"
        logger.info(f"[{self.name}] Connecting to SSE: {sse_url}")

        try:
            # Start the SSE listener task
            self.sse_task = asyncio.create_task(self._sse_listener())

            # Wait for connection to be established and client ID received
            await asyncio.sleep(0.5)

            if hasattr(self, 'client_id') and self.client_id:
                self.connected = True
                logger.info(f"[{self.name}] SSE connected with client ID: {self.client_id}")
            else:
                raise RuntimeError("Failed to receive client ID from SSE server")

        except Exception as e:
            logger.error(f"[{self.name}] Failed to connect via SSE: {e}")
            self.connected = False
            raise

    async def _sse_listener(self):
        """Listen for SSE messages"""
        sse_url = f"http://{self.server_url}/sse"

        try:
            async with self.session.get(sse_url) as response:
                if response.status != 200:
                    logger.error(f"[{self.name}] SSE connection failed: {response.status}")
                    return

                async for line in response.content:
                    line = line.decode('utf-8').strip()

                    if line.startswith('data: '):
                        data_str = line[6:]  # Remove 'data: ' prefix

                        try:
                            message = json.loads(data_str)

                            # Handle connection message to get client ID
                            if message.get('type') == 'connected':
                                self.client_id = message.get('client_id')
                                logger.info(f"[{self.name}] Received client ID: {self.client_id}")
                                continue
                            elif message.get('type') == 'ping':
                                logger.debug(f"[{self.name}] SSE ping received")
                                continue

                            # Handle MCP response messages
                            message_id = message.get('id')
                            if message_id and message_id in self.sse_responses:
                                # Complete the waiting future
                                future = self.sse_responses.pop(message_id)
                                if not future.done():
                                    future.set_result(message)
                            else:
                                logger.info(f"[{self.name}] SSE notification: {message}")

                        except json.JSONDecodeError:
                            logger.warning(f"[{self.name}] Invalid SSE JSON: {data_str}")
                        except Exception as e:
                            logger.error(f"[{self.name}] SSE processing error: {e}")

        except Exception as e:
            logger.error(f"[{self.name}] SSE listener error: {e}")
            self.connected = False

    async def send_message(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send MCP message and wait for response"""
        if not self.connected:
            raise RuntimeError(f"[{self.name}] Not connected to server")

        if params is None:
            params = {}

        self.message_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self.message_id,
            "method": method,
            "params": params
        }

        logger.info(f"[{self.name}] Sending: {method}")

        if self.transport == "websocket":
            await self.ws.send_str(json.dumps(message))

            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    response = json.loads(msg.data)

                    if response.get("id") == self.message_id:
                        return response
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"[{self.name}] WebSocket error: {self.ws.exception()}")
                    self.connected = False
                    break

        elif self.transport == "sse":
            # For SSE, send via HTTP POST and wait for response via SSE stream
            post_url = f"http://{self.server_url}/message"

            # Create a future to wait for the response
            response_future = asyncio.Future()
            self.sse_responses[self.message_id] = response_future

            # Add client ID to the POST request
            headers = {}
            if hasattr(self, 'client_id') and self.client_id:
                headers['X-Client-ID'] = self.client_id

            try:
                async with self.session.post(post_url, json=message, headers=headers) as response:
                    if response.status not in [200, 202]:
                        self.sse_responses.pop(self.message_id, None)
                        raise RuntimeError(f"HTTP POST failed: {response.status}")

                # Wait for response via SSE
                try:
                    result = await asyncio.wait_for(response_future, timeout=30.0)
                    return result
                except asyncio.TimeoutError:
                    self.sse_responses.pop(self.message_id, None)
                    raise RuntimeError("SSE response timeout")

            except Exception as e:
                self.sse_responses.pop(self.message_id, None)
                raise

        return {}

    async def initialize(self):
        """Initialize MCP connection"""
        response = await self.send_message("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "multi-server-mcp-client",
                "version": "1.0.0"
            }
        })

        if "error" in response:
            logger.error(f"[{self.name}] Initialize failed: {response['error']}")
            return False

        result = response.get("result", {})
        self.capabilities = result.get("capabilities", {})
        logger.info(f"[{self.name}] MCP connection initialized successfully")
        return True

    async def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        response = await self.send_message("tools/list")
        return response.get("result", {})

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool"""
        response = await self.send_message("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        return response.get("result", {})

    async def list_resources(self) -> Dict[str, Any]:
        """List available resources"""
        response = await self.send_message("resources/list")
        return response.get("result", {})

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a specific resource"""
        response = await self.send_message("resources/read", {
            "uri": uri
        })
        return response.get("result", {})

    async def close(self):
        """Close connection"""
        self.connected = False

        if self.sse_task:
            self.sse_task.cancel()
            try:
                await self.sse_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()


class MultiServerMCPClient:
    """Client that can manage multiple MCP server connections"""

    def __init__(self):
        self.connections: Dict[str, MCPConnection] = {}

    async def add_server(self, name: str, server_url: str, transport: str = "websocket"):
        """Add a new server connection"""
        if name in self.connections:
            logger.warning(f"Server '{name}' already exists, replacing...")
            await self.remove_server(name)

        connection = MCPConnection(name, server_url, transport)
        self.connections[name] = connection

        try:
            await connection.connect()
            await connection.initialize()
            logger.info(f"Successfully added server '{name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to add server '{name}': {e}")
            if name in self.connections:
                del self.connections[name]
            return False

    async def remove_server(self, name: str):
        """Remove a server connection"""
        if name in self.connections:
            await self.connections[name].close()
            del self.connections[name]
            logger.info(f"Removed server '{name}'")

    def get_server(self, name: str) -> Optional[MCPConnection]:
        """Get a specific server connection"""
        return self.connections.get(name)

    def list_servers(self) -> List[str]:
        """List all connected servers"""
        return list(self.connections.keys())

    async def broadcast_to_all(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a message to all connected servers"""
        results = {}

        for name, connection in self.connections.items():
            if connection.connected:
                try:
                    result = await connection.send_message(method, params)
                    results[name] = result
                except Exception as e:
                    logger.error(f"[{name}] Error during broadcast: {e}")
                    results[name] = {"error": str(e)}
            else:
                results[name] = {"error": "Not connected"}

        return results

    async def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get tools from all servers"""
        all_tools = {}

        for name, connection in self.connections.items():
            if connection.connected:
                try:
                    tools_result = await connection.list_tools()
                    all_tools[name] = tools_result.get("tools", [])
                except Exception as e:
                    logger.error(f"[{name}] Error getting tools: {e}")
                    all_tools[name] = []
            else:
                all_tools[name] = []

        return all_tools

    async def call_tool_on_server(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool on a specific server"""
        connection = self.get_server(server_name)
        if not connection:
            return {"error": f"Server '{server_name}' not found"}

        if not connection.connected:
            return {"error": f"Server '{server_name}' not connected"}

        try:
            return await connection.call_tool(tool_name, arguments)
        except Exception as e:
            return {"error": str(e)}

    async def close_all(self):
        """Close all connections"""
        for connection in self.connections.values():
            await connection.close()
        self.connections.clear()


def parse_arguments(args_str: str) -> Dict[str, Any]:
    """Parse arguments string into proper format for MCP tools"""
    args_str = args_str.strip()

    if not args_str:
        return {}

    # Try to parse as JSON first
    try:
        parsed = json.loads(args_str)
        # If it parses as JSON and is a dict, use it as-is
        if isinstance(parsed, dict):
            return parsed
        # If it's a string or other type from JSON, handle specially
        elif isinstance(parsed, str):
            # For simple string arguments, assume it's a message for echo-like tools
            return {"message": parsed}
        else:
            # For other JSON types (numbers, arrays, etc.), convert to message
            return {"message": str(parsed)}
    except json.JSONDecodeError:
        # If it's not valid JSON, treat it as a simple string
        # For most tools, we'll assume it's a message parameter
        return {"message": args_str}


async def test_multiple_servers(client: MultiServerMCPClient):
    """Test functionality across multiple servers"""
    print("\n=== Multi-Server Testing ===")

    # Get tools from all servers
    all_tools = await client.get_all_tools()

    for server_name, tools in all_tools.items():
        print(f"\n--- Server '{server_name}' tools ---")
        for tool in tools:
            print(f"  {tool['name']}: {tool['description']}")

    # Test same tool across different servers
    print("\n--- Testing 'echo' tool across all servers ---")
    for server_name in client.list_servers():
        result = await client.call_tool_on_server(server_name, "echo", {"message": f"Hello from {server_name}!"})
        print(f"[{server_name}] {result}")

    # Broadcast a command to all servers
    print("\n--- Broadcasting 'get_time' to all servers ---")
    broadcast_results = await client.broadcast_to_all("tools/call", {
        "name": "get_time",
        "arguments": {}
    })

    for server_name, result in broadcast_results.items():
        if "error" not in result:
            content = result.get("result", {}).get("content", [])
            if content:
                print(f"[{server_name}] {content[0].get('text', 'No text')}")
        else:
            print(f"[{server_name}] Error: {result['error']}")


async def interactive_multi_server_mode(client: MultiServerMCPClient):
    """Interactive mode for multi-server testing"""
    print("\n=== Multi-Server Interactive Mode ===")
    print("Available commands:")
    print("  servers - List connected servers")
    print("  tools [server_name] - List tools (all servers or specific server)")
    print("  call <server_name> <tool_name> <args> - Call tool on specific server")
    print("    Args can be JSON: {\"key\": \"value\"} or simple text for message-based tools")
    print("  broadcast <tool_name> <args> - Call tool on all servers")
    print("  add <name> <host:port> [transport] - Add new server")
    print("  remove <name> - Remove server")
    print("  quit - Exit")
    print("\nExamples:")
    print("  call server1 echo hello")
    print("  call server1 echo {\"message\": \"hello world\"}")
    print("  call server1 math_calc {\"expression\": \"2 + 2\"}")
    print("  broadcast get_time")

    while True:
        try:
            command = input("\n> ").strip()

            if command == "quit":
                break
            elif command == "servers":
                servers = client.list_servers()
                print(f"Connected servers: {servers}")
            elif command.startswith("tools"):
                parts = command.split()
                if len(parts) == 1:
                    # All servers
                    all_tools = await client.get_all_tools()
                    for server_name, tools in all_tools.items():
                        print(f"\n[{server_name}]:")
                        for tool in tools:
                            print(f"  {tool['name']}: {tool['description']}")
                else:
                    # Specific server
                    server_name = parts[1]
                    connection = client.get_server(server_name)
                    if connection:
                        result = await connection.list_tools()
                        tools = result.get("tools", [])
                        for tool in tools:
                            print(f"  {tool['name']}: {tool['description']}")
                    else:
                        print(f"Server '{server_name}' not found")
            elif command.startswith("call "):
                parts = command.split(" ", 3)
                if len(parts) >= 3:
                    server_name = parts[1]
                    tool_name = parts[2]
                    args_str = parts[3] if len(parts) > 3 else ""

                    # Parse arguments using our new function
                    args = parse_arguments(args_str)

                    result = await client.call_tool_on_server(server_name, tool_name, args)
                    print(f"Result: {result}")
                else:
                    print("Usage: call <server_name> <tool_name> [args]")
            elif command.startswith("broadcast "):
                parts = command.split(" ", 2)
                if len(parts) >= 2:
                    tool_name = parts[1]
                    args_str = parts[2] if len(parts) > 2 else ""

                    # Parse arguments using our new function
                    args = parse_arguments(args_str)

                    results = await client.broadcast_to_all("tools/call", {
                        "name": tool_name,
                        "arguments": args
                    })
                    for server_name, result in results.items():
                        print(f"[{server_name}] {result}")
                else:
                    print("Usage: broadcast <tool_name> [args]")
            elif command.startswith("add "):
                parts = command.split(" ")
                if len(parts) >= 3:
                    name = parts[1]
                    server_url = parts[2]
                    transport = parts[3] if len(parts) > 3 else "websocket"
                    success = await client.add_server(name, server_url, transport)
                    print(f"Add server {'succeeded' if success else 'failed'}")
                else:
                    print("Usage: add <name> <host:port> [transport]")
            elif command.startswith("remove "):
                parts = command.split(" ", 1)
                if len(parts) == 2:
                    name = parts[1]
                    await client.remove_server(name)
                else:
                    print("Usage: remove <name>")
            else:
                print("Unknown command")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")


async def main():
    parser = argparse.ArgumentParser(description="Multi-Server MCP Client")
    parser.add_argument("servers", nargs="+", help="Server addresses in format name=host:port")
    parser.add_argument("--transport", choices=["websocket", "sse"],
                        default="websocket", help="Transport protocol")
    parser.add_argument("--mode", choices=["test", "interactive"],
                        default="interactive", help="Run mode")

    args = parser.parse_args()

    client = MultiServerMCPClient()

    try:
        # Connect to all specified servers
        for server_spec in args.servers:
            if "=" in server_spec:
                name, server_url = server_spec.split("=", 1)
            else:
                # Default naming
                name = f"server_{len(client.connections) + 1}"
                server_url = server_spec

            await client.add_server(name, server_url, args.transport)

        if not client.connections:
            print("No servers connected successfully")
            return

        print(f"Connected to {len(client.connections)} servers: {client.list_servers()}")

        if args.mode == "test":
            await test_multiple_servers(client)
        else:
            await interactive_multi_server_mode(client)

    except Exception as e:
        logger.error(f"Client error: {e}")
    finally:
        await client.close_all()


if __name__ == "__main__":
    # Example usage:
    # python multi_server_client.py server1=192.168.1.100:8080 server2=192.168.1.101:8080
    # python multi_server_client.py 192.168.1.100:8080 192.168.1.101:8080 --mode test
    # python multi_server_client.py server1=localhost:8080 --transport sse
    asyncio.run(main())