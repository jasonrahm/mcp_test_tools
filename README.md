# MCP Multi-Server Client Documentation

## Table of Contents
1. [Introduction to MCP](#introduction-to-mcp)
2. [Project Overview](#project-overview)
3. [Setup and Installation](#setup-and-installation)
4. [Starting Multiple Servers](#starting-multiple-servers)
5. [Starting the Client](#starting-the-client)
6. [Testing Scenarios](#testing-scenarios)
7. [Interactive Commands](#interactive-commands)
8. [Troubleshooting](#troubleshooting)

## Introduction to MCP

### What is MCP?
**Model Context Protocol (MCP)** is a standardized protocol for enabling AI models to interact with external tools and resources. It provides a structured way for AI systems to:

- **Call tools** - Execute functions and commands
- **Access resources** - Read files, databases, and other data sources
- **Communicate** - Exchange messages using a standardized format

### Key MCP Concepts

**Tools**: Functions that can be called by the AI model, such as:
- `echo` - Return a message
- `get_time` - Get current server time
- `list_files` - List directory contents
- `run_command` - Execute shell commands
- `math_calc` - Perform calculations

**Resources**: Data sources that can be read, such as:
- Server information
- System statistics
- Files and databases

**Transport Layers**: How messages are sent between client and server:
- **WebSocket** - Full bidirectional real-time communication
- **SSE (Server-Sent Events)** - HTTP-based streaming with POST for client-to-server

**Message Format**: JSON-RPC 2.0 protocol with standardized methods like:
- `initialize` - Set up connection
- `tools/list` - Get available tools
- `tools/call` - Execute a tool
- `resources/list` - Get available resources
- `resources/read` - Read a resource

## Project Overview

This project implements a **multi-server MCP client** that can:
- Connect to multiple MCP servers simultaneously
- Support both WebSocket and SSE transports
- Mix different transport types in a single session
- Broadcast commands to all connected servers
- Route tool calls to specific servers

### Architecture

```
Client (mcp_client.py)
├── MultiServerMCPClient
│   ├── MCPConnection (WebSocket)
│   ├── MCPConnection (SSE)
│   └── MCPConnection (WebSocket)
└── Interactive/Test modes

Server (mcp_server.py)
├── WebSocket Handler (/ws)
├── SSE Handler (/sse)
├── Message Handler (/message)
└── Tool/Resource Handlers
```

## Setup and Installation

### Prerequisites
This project uses `uv` for Python package management. Install uv if you haven't already:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# or
pip install uv
```

### Project Setup
```bash
# Initialize project with uv
uv init mcp-multi-server
cd mcp-multi-server

# Add dependencies
uv add aiohttp aiohttp-cors

# Or install from requirements if provided
uv sync
```

### File Structure
```
project/
├── mcp_client.py    # Multi-server MCP client
├── mcp_server.py    # MCP server with WebSocket/SSE support
├── pyproject.toml   # uv project configuration
├── uv.lock          # uv lock file
├── README.md        # This documentation
├── bigip.conf       # BIG-IP configuration used for MCP testing
├── JSON.irul        # iRule Procs library to parse JSON RPC 2.0 (some custom procs for named keys)
└── mcp_proxy.irul   # iRule to investigate MCP traffic through BIG-IP
```

### Verify Installation
```bash
# Run with uv
uv run python mcp_server.py --help
uv run python mcp_client.py --help

# Or activate virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
python mcp_server.py --help
python mcp_client.py --help
```

## Starting Multiple Servers

### Basic Server Startup
Start servers on different ports to test multi-server functionality:

```bash
# Terminal 1 - Server on port 8080
uv run python mcp_server.py --port 8080

# Terminal 2 - Server on port 8081  
uv run python mcp_server.py --port 8081

# Terminal 3 - Server on port 8082
uv run python mcp_server.py --port 8082
```

### Server Configuration Options

#### Custom Server Names
Use the `--name` option to give your servers meaningful names:

```bash
# Math-focused server
uv run python mcp_server.py --port 8080 --name "math-server"

# File operations server
uv run python mcp_server.py --port 8081 --name "file-server"

# General purpose server
uv run python mcp_server.py --port 8082 --name "general-server"
```

#### Tool Filtering
Use the `--tools` option to enable only specific tools on each server:

```bash
# Server with only math and echo tools
uv run python mcp_server.py --port 8080 --name "math-server" --tools math_calc echo

# Server with only file operations
uv run python mcp_server.py --port 8081 --name "file-server" --tools list_files echo

# Server with command execution capabilities
uv run python mcp_server.py --port 8082 --name "admin-server" --tools run_command get_time echo

# Server with all tools (default behavior)
uv run python mcp_server.py --port 8083 --name "full-server"
```

#### Available Tools
The server supports these tools (use any combination with `--tools`):
- `echo` - Echo back messages
- `get_time` - Get current server time
- `list_files` - List directory contents
- `run_command` - Execute shell commands
- `math_calc` - Perform calculations

#### Complete Server Configuration Examples
```bash
# Specialized servers for different purposes
uv run python mcp_server.py --host 127.0.0.1 --port 8080 --name "calculator" --tools math_calc echo
uv run python mcp_server.py --host 127.0.0.1 --port 8081 --name "filesystem" --tools list_files echo
uv run python mcp_server.py --host 127.0.0.1 --port 8082 --name "timekeeper" --tools get_time echo
uv run python mcp_server.py --host 127.0.0.1 --port 8083 --name "admin" --tools run_command get_time list_files
```

### Server with Custom Host
```bash
# Bind to specific interface
uv run python mcp_server.py --host 127.0.0.1 --port 8080

# Bind to all interfaces (default)
uv run python mcp_server.py --host 0.0.0.0 --port 8080
```

### Server Endpoints
Each server provides:
- **WebSocket**: `ws://localhost:8080/ws`
- **SSE Stream**: `http://localhost:8080/sse`
- **SSE Messages**: `http://localhost:8080/message`

## Starting the Client

### Basic Client Usage
```bash
# Connect to single server
uv run python mcp_client.py localhost:8080

# Connect to multiple servers with auto-naming
uv run python mcp_client.py localhost:8080 localhost:8081

# Connect with custom server names
uv run python mcp_client.py server1=localhost:8080 server2=localhost:8081
```

### Transport Selection
```bash
# Use WebSocket (default)
uv run python mcp_client.py server1=localhost:8080 --transport websocket

# Use SSE
uv run python mcp_client.py server1=localhost:8080 --transport sse
```

### Run Modes
```bash
# Interactive mode (default)
uv run python mcp_client.py localhost:8080 --mode interactive

# Test mode (automated testing)
uv run python mcp_client.py localhost:8080 --mode test
```

## Testing Scenarios

### 1. Single Server, Single Transport

#### WebSocket Testing
```bash
# Start server
uv run python mcp_server.py --port 8080

# Start client (in another terminal)
uv run python mcp_client.py server1=localhost:8080 --transport websocket

# In interactive mode:
> tools
> call server1 echo {"message": "Hello WebSocket!"}
> call server1 get_time {}
```

#### SSE Testing
```bash
# Start server
uv run python mcp_server.py --port 8080

# Start client (in another terminal)
uv run python mcp_client.py server1=localhost:8080 --transport sse

# In interactive mode:
> tools
> call server1 echo {"message": "Hello SSE!"}
> call server1 get_time {}
```

### 2. Multiple Servers, Single Transport

#### Multiple WebSocket Servers
```bash
# Start servers (in separate terminals)
uv run python mcp_server.py --port 8080 &
uv run python mcp_server.py --port 8081 &
uv run python mcp_server.py --port 8082 &

# Start client (in another terminal)
uv run python mcp_client.py ws1=localhost:8080 ws2=localhost:8081 ws3=localhost:8082 --transport websocket

# Test commands:
> servers
> tools
> broadcast echo {"message": "Hello all servers!"}
> call ws1 get_time {}
> call ws2 list_files {"path": "."}
```

#### Multiple SSE Servers
```bash
# Start servers (in separate terminals)
uv run python mcp_server.py --port 8080 &
uv run python mcp_server.py --port 8081 &

# Start client (in another terminal)
uv run python mcp_client.py sse1=localhost:8080 sse2=localhost:8081 --transport sse

# Test commands:
> servers
> broadcast get_time {}
> call sse1 echo {"message": "SSE Server 1"}
> call sse2 echo {"message": "SSE Server 2"}
```

### 3. Specialized Server Testing

#### Math and File Servers
```bash
# Start specialized servers (in separate terminals)
uv run python mcp_server.py --port 8080 --name "calculator" --tools math_calc echo &
uv run python mcp_server.py --port 8081 --name "filesystem" --tools list_files echo &

# Start client (in another terminal)
uv run python mcp_client.py calc=localhost:8080 files=localhost:8081 --transport websocket

# Test specialized functionality:
> tools
> call calc math_calc {"expression": "2 + 2 * 3"}
> call files list_files {"path": "."}
> call calc list_files {"path": "."} # This should fail - tool not enabled
```

#### Tool Filtering Demonstration
```bash
# Start servers with different tool sets
uv run python mcp_server.py --port 8080 --name "math-only" --tools math_calc &
uv run python mcp_server.py --port 8081 --name "time-only" --tools get_time &
uv run python mcp_server.py --port 8082 --name "full-server" &

# Connect client
uv run python mcp_client.py math=localhost:8080 time=localhost:8081 full=localhost:8082

# Test tool availability:
> tools math    # Should only show math_calc
> tools time    # Should only show get_time  
> tools full    # Should show all tools
> call math math_calc {"expression": "10 * 5"}
> call time get_time {}
> call math get_time {} # Should fail - tool not enabled
```

### 4. Mixed Transport Testing

Start with one transport, then add servers with different transports:

```bash
# Start servers (in separate terminals)
uv run python mcp_server.py --port 8080 --name "ws-server" &
uv run python mcp_server.py --port 8081 --name "sse-server-1" &
uv run python mcp_server.py --port 8082 --name "sse-server-2" &

# Start client with WebSocket (in another terminal)
uv run python mcp_client.py ws1=localhost:8080 --transport websocket

# In interactive mode, add SSE servers:
> add sse1 localhost:8081 sse
> add sse2 localhost:8082 sse

# Test mixed environment:
> servers
> tools
> call ws1 echo {"message": "WebSocket server"}
> call sse1 echo {"message": "SSE server 1"}
> call sse2 echo {"message": "SSE server 2"}
> broadcast get_time {}
```

### 5. Advanced Testing Scenarios

#### Stress Testing
```bash
# Test with many tool calls
> call server1 math_calc {"expression": "2 + 2"}
> call server1 math_calc {"expression": "10 * 5"}
> call server1 math_calc {"expression": "100 / 4"}

# Test file operations
> call server1 list_files {"path": "/tmp"}
> call server1 list_files {"path": "."}
```

#### Error Handling
```bash
# Test invalid tool calls
> call server1 nonexistent_tool {}
> call server1 math_calc {"expression": "invalid"}
> call server1 list_files {"path": "/nonexistent"}

# Test disabled tools (when using --tools filter)
> call math-server list_files {"path": "."} # Should fail if list_files not enabled

# Test server failures
> call nonexistent_server echo {"message": "test"}
```

#### Resource Testing
```bash
# Test server info resource (includes enabled tools information)
> call server1 resources/list {}
> call server1 resources/read {"uri": "server://info"}
```

## Interactive Commands

### Server Management
- `servers` - List all connected servers
- `add <name> <host:port> [transport]` - Add new server
- `remove <name>` - Remove server connection

### Tool Operations
- `tools` - List tools from all servers
- `tools <server_name>` - List tools from specific server
- `call <server_name> <tool_name> <json_args>` - Call tool on specific server
- `broadcast <tool_name> <json_args>` - Call tool on all servers

### System Commands
- `quit` - Exit the client

### Example Session with Named Servers
```bash
$ uv run python mcp_client.py calc=localhost:8080 files=localhost:8081 --transport websocket

> servers
Connected servers: ['calc', 'files']

> tools calc
[calc]:
  math_calc: Perform basic math calculations
  echo: Echo back the provided message

> tools files  
[files]:
  list_files: List files in a directory
  echo: Echo back the provided message

> call calc math_calc {"expression": "2 + 2 * 3"}
Result: {'content': [{'type': 'text', 'text': '2 + 2 * 3 = 8'}]}

> call files list_files {"path": "."}
Result: {'content': [{'type': 'text', 'text': 'Files in .:\nmcp_client.py\nmcp_server.py\nREADME.md'}]}

> add admin localhost:8082 sse
Add server succeeded

> servers
Connected servers: ['calc', 'files', 'admin']

> broadcast echo {"message": "Hello from all servers!"}
[calc] {'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': 'Echo: Hello from all servers!'}]}}
[files] {'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': 'Echo: Hello from all servers!'}]}}
[admin] {'jsonrpc': '2.0', 'id': 1, 'result': {'content': [{'type': 'text', 'text': 'Echo: Hello from all servers!'}]}}

> quit
```

## Troubleshooting

### Common Issues

#### Connection Failures
**Problem**: `Failed to add server: Not connected to server`
**Solutions**:
- Ensure server is running on specified port
- Check firewall settings
- Verify correct host/port combination
- For SSE, ensure both `/sse` and `/message` endpoints are accessible

#### Tool Not Available Errors
**Problem**: `Tool 'toolname' is not enabled on this server`
**Solutions**:
- Check which tools are enabled with `tools <server_name>` command
- Restart server with desired tools using `--tools` option
- Use `call <server_name> resources/read {"uri": "server://info"}` to see enabled tools
- Ensure you're calling the correct server that has the desired tool

#### SSE-Specific Issues
**Problem**: SSE connection drops or timeouts
**Solutions**:
- Check server logs for connection errors
- Verify client ID is being properly tracked
- Ensure HTTP POST requests reach `/message` endpoint
- Check for proxy/firewall interference with SSE streams

#### Transport Mixing Issues
**Problem**: Commands fail on specific transport types
**Solutions**:
- Test each transport individually first
- Check server support for both WebSocket and SSE
- Verify client transport selection logic
- Monitor server logs for transport-specific errors

### Debug Mode
Enable detailed logging:
```bash
# Server with debug logging and specific configuration
uv run python mcp_server.py --port 8080 --name "debug-server" --tools echo get_time 2>&1 | tee server.log

# Client with debug info
uv run python mcp_client.py server1=localhost:8080 2>&1 | tee client.log
```

### Server Configuration Verification
Check that your server configuration is working as expected:

```bash
# Start server with specific tools
uv run python mcp_server.py --port 8080 --name "test-server" --tools echo math_calc

# In another terminal, connect and verify
uv run python mcp_client.py test=localhost:8080

# In client:
> call test resources/read {"uri": "server://info"}
# Should show server name and enabled tools list
```

### Testing Checklist
- [ ] Single server WebSocket connection
- [ ] Single server SSE connection  
- [ ] Multiple servers same transport
- [ ] Multiple servers mixed transport
- [ ] Tool calls work on all servers
- [ ] Tool filtering works correctly
- [ ] Server naming appears in responses
- [ ] Broadcast commands work
- [ ] Error handling works for disabled tools
- [ ] Server addition/removal works
- [ ] Interactive commands work
- [ ] Connection cleanup works

### Performance Considerations
- SSE connections use HTTP/1.1 streaming (may have higher latency)
- WebSocket connections provide lower latency
- Multiple servers increase resource usage
- Broadcast operations are executed sequentially
- Tool filtering reduces memory usage and attack surface

### Security Notes
- The `run_command` tool executes shell commands (use with caution)
- Use tool filtering to disable dangerous tools in production
- Math evaluation uses `eval()` with restricted builtins
- No authentication implemented (suitable for testing only)
- CORS is enabled for all origins (development only)
- Consider running servers with minimal tool sets for security

## Next Steps

1. **Extend Tools**: Add more sophisticated tools and resources
2. **Add Authentication**: Implement proper security measures
3. **Tool Permissions**: Add role-based tool access
4. **Monitoring**: Add health checks and monitoring
5. **Performance**: Optimize for high-throughput scenarios
6. **Integration**: Connect with AI models and other systems
7. **Dynamic Configuration**: Allow runtime tool enabling/disabling

For more information about MCP specification, visit the official MCP documentation.