#!/usr/bin/env python3
"""
MCP Server with WebSocket and SSE support
Includes multiple test tools for comprehensive testing
Now with proper bidirectional SSE support
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
import weakref

from aiohttp import web, WSMsgType
from aiohttp.web_request import Request
from aiohttp.web_response import Response
from aiohttp.web_ws import WebSocketResponse
import aiohttp_cors

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """Manages SSE connections and message routing"""

    def __init__(self):
        self.connections: Dict[str, web.StreamResponse] = {}
        self.pending_messages: Dict[str, List[Dict[str, Any]]] = {}

    def add_connection(self, client_id: str, response: web.StreamResponse):
        """Add a new SSE connection"""
        self.connections[client_id] = response
        logger.info(f"SSE client {client_id} connected")

    def remove_connection(self, client_id: str):
        """Remove an SSE connection"""
        if client_id in self.connections:
            del self.connections[client_id]
            logger.info(f"SSE client {client_id} disconnected")

    async def send_to_client(self, client_id: str, message: Dict[str, Any]):
        """Send a message to a specific SSE client"""
        if client_id in self.connections:
            try:
                response = self.connections[client_id]
                data = json.dumps(message)
                await response.write(f"data: {data}\n\n".encode())
                return True
            except Exception as e:
                logger.error(f"Failed to send to SSE client {client_id}: {e}")
                self.remove_connection(client_id)
                return False
        return False


class MCPServer:
    def __init__(self, server_name: str = "multi-tool-mcp-server", enabled_tools: Optional[List[str]] = None):
        self.server_name = server_name

        # Define all available tools
        self.all_tools = {
            "echo": {
                "name": "echo",
                "description": "Echo back the provided message",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to echo"}
                    },
                    "required": ["message"]
                }
            },
            "get_time": {
                "name": "get_time",
                "description": "Get current server time",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            "list_files": {
                "name": "list_files",
                "description": "List files in a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to list"}
                    },
                    "required": ["path"]
                }
            },
            "run_command": {
                "name": "run_command",
                "description": "Execute a shell command (be careful!)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"}
                    },
                    "required": ["command"]
                }
            },
            "math_calc": {
                "name": "math_calc",
                "description": "Perform basic math calculations",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "Math expression to evaluate"}
                    },
                    "required": ["expression"]
                }
            }
        }

        # Filter tools based on enabled_tools parameter
        if enabled_tools is None:
            self.tools = self.all_tools
        else:
            self.tools = {name: tool for name, tool in self.all_tools.items() if name in enabled_tools}

        # Log which tools are enabled
        logger.info(f"Enabled tools: {list(self.tools.keys())}")

        self.resources = {
            "server_info": {
                "uri": "server://info",
                "name": "Server Information",
                "description": "Information about this MCP server",
                "mimeType": "application/json"
            },
            "system_stats": {
                "uri": "server://stats",
                "name": "System Statistics",
                "description": "Basic system statistics",
                "mimeType": "application/json"
            }
        }

        self.sse_manager = SSEConnectionManager()

    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP initialize request"""
        logger.info(f"Initialize request: {params}")

        response = {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "serverInfo": {
                "name": self.server_name,
                "version": "1.0.0"
            }
        }

        logger.info(f"Initialize response: {response}")
        return response

    async def handle_list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request"""
        return {
            "tools": list(self.tools.values())
        }

    async def handle_list_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/list request"""
        return {
            "resources": list(self.resources.values())
        }

    async def handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        # Handle case where arguments might be a string instead of dict
        if isinstance(arguments, str):
            logger.warning(f"Received string arguments instead of object: {arguments}")
            # For echo tool, if we get a string, treat it as the message
            if tool_name == "echo":
                arguments = {"message": arguments}
            else:
                # For other tools, we can't easily convert, so return an error
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Tool '{tool_name}' expects object arguments, got string: {arguments}"
                    }],
                    "isError": True
                }

        logger.info(f"Tool call: {tool_name} with args: {arguments}")

        # Check if tool is enabled
        if tool_name not in self.tools:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Tool '{tool_name}' is not enabled on this server"
                }],
                "isError": True
            }

        if tool_name == "echo":
            return {
                "content": [{
                    "type": "text",
                    "text": f"Echo: {arguments.get('message', '')}"
                }]
            }

        elif tool_name == "get_time":
            return {
                "content": [{
                    "type": "text",
                    "text": f"Current server time: {datetime.now().isoformat()}"
                }]
            }

        elif tool_name == "list_files":
            path = arguments.get("path", ".")
            try:
                files = os.listdir(path)
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Files in {path}:\n" + "\n".join(files)
                    }]
                }
            except Exception as e:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error listing files: {str(e)}"
                    }],
                    "isError": True
                }

        elif tool_name == "run_command":
            command = arguments.get("command", "")
            try:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Command: {command}\nReturn code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
                    }]
                }
            except Exception as e:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error running command: {str(e)}"
                    }],
                    "isError": True
                }

        elif tool_name == "math_calc":
            expression = arguments.get("expression", "")
            try:
                # Simple and safe math evaluation
                result = eval(expression, {"__builtins__": {}}, {})
                return {
                    "content": [{
                        "type": "text",
                        "text": f"{expression} = {result}"
                    }]
                }
            except Exception as e:
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error calculating: {str(e)}"
                    }],
                    "isError": True
                }

        else:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Unknown tool: {tool_name}"
                }],
                "isError": True
            }

    async def handle_read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request"""
        uri = params.get("uri")

        if uri == "server://info":
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "server": self.server_name,
                        "version": "1.0.0",
                        "tools_count": len(self.tools),
                        "resources_count": len(self.resources),
                        "enabled_tools": list(self.tools.keys())
                    })
                }]
            }

        elif uri == "server://stats":
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps({
                        "timestamp": datetime.now().isoformat(),
                        "uptime": "N/A",
                        "memory_usage": "N/A"
                    })
                }]
            }

        else:
            return {
                "contents": [{
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": f"Resource not found: {uri}"
                }]
            }

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP message"""
        # Add debugging to catch type issues
        if not isinstance(message, dict):
            logger.error(f"Expected dict but got {type(message)}: {message}")
            return {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32600,
                    "message": f"Invalid request: expected object, got {type(message).__name__}"
                }
            }

        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        try:
            if method == "initialize":
                result = await self.handle_initialize(params)
            elif method == "tools/list":
                result = await self.handle_list_tools(params)
            elif method == "tools/call":
                result = await self.handle_call_tool(params)
            elif method == "resources/list":
                result = await self.handle_list_resources(params)
            elif method == "resources/read":
                result = await self.handle_read_resource(params)
            else:
                result = {
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }

            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": result
            }

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }

        return response

    async def websocket_handler(self, request: Request) -> WebSocketResponse:
        """Handle WebSocket connections"""
        ws = WebSocketResponse()
        await ws.prepare(request)

        logger.info(f"WebSocket connection from {request.remote}")

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    logger.info(f"WebSocket received: {data} (type: {type(data)})")

                    response = await self.handle_message(data)
                    await ws.send_str(json.dumps(response))

                except json.JSONDecodeError:
                    await ws.send_str(json.dumps({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"}
                    }))

            elif msg.type == WSMsgType.ERROR:
                logger.error(f'WebSocket error: {ws.exception()}')
                break

        logger.info("WebSocket connection closed")
        return ws


    async def sse_handler(self, request: Request) -> Response:
        """Handle SSE connections - server-to-client stream"""
        response = web.StreamResponse(
            status=200,
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Cache-Control'
            }
        )

        await response.prepare(request)

        # Generate a unique client ID from query params or request
        client_id = request.query.get('client_id', f"client_{hash(str(request.remote) + str(id(request)))}")

        # Add to connection manager
        self.sse_manager.add_connection(client_id, response)

        logger.info(f"SSE connection from {request.remote} (client_id: {client_id})")

        # Send initial connection message with client ID
        try:
            await response.write(f'data: {{"type": "connected", "client_id": "{client_id}"}}\n\n'.encode())
        except Exception as e:
            logger.error(f"Failed to send connection message: {e}")
            self.sse_manager.remove_connection(client_id)
            return response

        # Keep connection alive and handle cleanup
        try:
            # Wait for the connection to be closed by the client
            while not response.task.done():
                await asyncio.sleep(30)
                # Send periodic ping to keep connection alive
                try:
                    await response.write(b'data: {"type": "ping"}\n\n')
                except Exception as e:
                    logger.error(f"Failed to send ping: {e}")
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"SSE connection error: {e}")
        finally:
            self.sse_manager.remove_connection(client_id)

        logger.info(f"SSE connection closed (client_id: {client_id})")
        return response


    async def message_handler(self, request: Request) -> Response:
        """Handle HTTP POST messages for SSE clients"""
        try:
            data = await request.json()
            logger.info(f"HTTP message received: {data} (type: {type(data)})")

            # Process the MCP message
            response = await self.handle_message(data)

            # Get client ID from headers or query parameters
            client_id = request.headers.get('X-Client-ID') or request.query.get('client_id')

            if client_id:
                # Send response via SSE
                sent = await self.sse_manager.send_to_client(client_id, response)

                if sent:
                    return web.Response(status=202, text="Message queued for SSE delivery")
                else:
                    logger.warning(f"SSE client {client_id} not found, returning direct response")
                    return web.json_response(response)
            else:
                # No client ID provided, return response directly
                return web.json_response(response)

        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"}
            }
            return web.json_response(error_response, status=400)
        except Exception as e:
            logger.error(f"Message handler error: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }
            return web.json_response(error_response, status=500)


async def create_app(server_name: str, enabled_tools: Optional[List[str]] = None) -> web.Application:
    """Create the web application"""
    app = web.Application()
    server = MCPServer(server_name=server_name, enabled_tools=enabled_tools)

    # Add routes
    app.router.add_get('/ws', server.websocket_handler)
    app.router.add_get('/sse', server.sse_handler)
    app.router.add_post('/message', server.message_handler)

    # Add CORS support
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*"
        )
    })

    # Add CORS to all routes
    for route in list(app.router.routes()):
        cors.add(route)

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Multi-tool MCP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--name", default="multi-tool-mcp-server", help="Server name")
    parser.add_argument("--tools", nargs="*",
                        choices=["echo", "get_time", "list_files", "run_command", "math_calc"],
                        help="Tools to enable (default: all tools)")

    args = parser.parse_args()

    # Handle tools argument
    enabled_tools = args.tools if args.tools else None

    app = create_app(server_name=args.name, enabled_tools=enabled_tools)

    print(f"Starting MCP server '{args.name}' on {args.host}:{args.port}")
    if enabled_tools:
        print(f"Enabled tools: {', '.join(enabled_tools)}")
    else:
        print("Enabled tools: all")
    print(f"WebSocket endpoint: ws://{args.host}:{args.port}/ws")
    print(f"SSE endpoint: http://{args.host}:{args.port}/sse")
    print(f"Message POST endpoint: http://{args.host}:{args.port}/message")

    web.run_app(app, host=args.host, port=args.port)