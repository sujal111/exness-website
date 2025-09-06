from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import asyncio
import websockets
import json
import logging
from typing import Set
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Binance Real-time Data API")

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.binance_ws = None
        self.is_connected = False

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")
        
        # Start Binance WebSocket connection if it's the first client
        if len(self.active_connections) == 1 and not self.is_connected:
            await self.start_binance_connection()

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")
            
            # Close Binance connection if no clients are connected
            if len(self.active_connections) == 0 and self.is_connected:
                await self.stop_binance_connection()

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if self.active_connections:
            disconnected = set()
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error sending message to client: {e}")
                    disconnected.add(connection)
            
            # Remove disconnected clients
            for conn in disconnected:
                self.active_connections.discard(conn)

    async def start_binance_connection(self):
        """Start connection to Binance WebSocket"""
        try:
            # Binance WebSocket URL for multiple streams
            # This example subscribes to BTCUSDT and ETHUSDT ticker data
            streams = [
                "btcusdt@ticker",
                "ethusdt@ticker",
                "adausdt@ticker",
                "bnbusdt@ticker"
            ]
            
            stream_names = "/".join(streams)
            binance_url = f"wss://stream.binance.com:9443/ws/{stream_names}"
            
            self.binance_ws = await websockets.connect(binance_url)
            self.is_connected = True
            logger.info("Connected to Binance WebSocket")
            
            # Start listening for messages
            asyncio.create_task(self.listen_binance_messages())
            
        except Exception as e:
            logger.error(f"Failed to connect to Binance WebSocket: {e}")
            self.is_connected = False

    async def stop_binance_connection(self):
        """Stop Binance WebSocket connection"""
        if self.binance_ws and not self.binance_ws.closed:
            await self.binance_ws.close()
            self.is_connected = False
            logger.info("Disconnected from Binance WebSocket")

    async def listen_binance_messages(self):
        """Listen for messages from Binance WebSocket"""
        try:
            while self.is_connected and self.binance_ws:
                try:
                    message = await asyncio.wait_for(self.binance_ws.recv(), timeout=30)
                    data = json.loads(message)
                    
                    # Process and format the data
                    formatted_data = self.format_binance_data(data)
                    
                    # Broadcast to all connected clients
                    await self.broadcast(formatted_data)
                    
                except asyncio.TimeoutError:
                    logger.warning("No message received from Binance in 30 seconds")
                    continue
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Binance WebSocket connection closed")
                    self.is_connected = False
                    break
                    
        except Exception as e:
            logger.error(f"Error in Binance message listener: {e}")
            self.is_connected = False

    def format_binance_data(self, data: dict) -> dict:
        """Format Binance ticker data for clients"""
        try:
            if 's' in data:  # Ticker data
                return {
                    "type": "ticker",
                    "symbol": data.get('s'),
                    "price": float(data.get('c', 0)),
                    "change": float(data.get('P', 0)),
                    "change_percent": f"{float(data.get('P', 0)):.2f}%",
                    "volume": float(data.get('v', 0)),
                    "high": float(data.get('h', 0)),
                    "low": float(data.get('l', 0)),
                    "timestamp": data.get('E')
                }
            else:
                return {"type": "unknown", "data": data}
        except Exception as e:
            logger.error(f"Error formatting Binance data: {e}")
            return {"type": "error", "message": "Data formatting error"}

# Initialize connection manager
manager = ConnectionManager()

@app.get("/")
async def get():
    """Serve a simple HTML page for testing"""
    html_content = """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Binance Real-time Data</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .ticker { 
                    border: 1px solid #ddd; 
                    margin: 10px 0; 
                    padding: 15px; 
                    border-radius: 5px;
                    background-color: #f9f9f9;
                }
                .price { font-size: 1.2em; font-weight: bold; }
                .positive { color: green; }
                .negative { color: red; }
                .status { margin-bottom: 20px; padding: 10px; border-radius: 5px; }
                .connected { background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
                .disconnected { background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            </style>
        </head>
        <body>
            <h1>Binance Real-time Cryptocurrency Data</h1>
            <div id="status" class="status disconnected">Disconnected</div>
            <div id="data"></div>
            
            <script>
                const ws = new WebSocket("ws://localhost:8000/ws");
                const statusDiv = document.getElementById('status');
                const dataDiv = document.getElementById('data');
                const tickers = {};
                
                ws.onopen = function(event) {
                    statusDiv.textContent = "Connected to real-time data feed";
                    statusDiv.className = "status connected";
                };
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    if (data.type === 'ticker') {
                        updateTicker(data);
                    }
                };
                
                ws.onclose = function(event) {
                    statusDiv.textContent = "Disconnected from data feed";
                    statusDiv.className = "status disconnected";
                };
                
                ws.onerror = function(event) {
                    statusDiv.textContent = "Connection error";
                    statusDiv.className = "status disconnected";
                };
                
                function updateTicker(data) {
                    const changeClass = parseFloat(data.change) >= 0 ? 'positive' : 'negative';
                    const tickerHtml = `
                        <div class="ticker">
                            <h3>${data.symbol}</h3>
                            <div class="price ${changeClass}">$${data.price.toFixed(4)}</div>
                            <div>Change: <span class="${changeClass}">${data.change_percent}</span></div>
                            <div>24h High: $${data.high.toFixed(4)}</div>
                            <div>24h Low: $${data.low.toFixed(4)}</div>
                            <div>24h Volume: ${data.volume.toFixed(2)}</div>
                        </div>
                    `;
                    
                    tickers[data.symbol] = tickerHtml;
                    dataDiv.innerHTML = Object.values(tickers).join('');
                }
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for clients to connect"""
    await manager.connect(websocket)
    try:
        # Keep connection alive
        while True:
            # Wait for any message from client (ping/pong or commands)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                # Echo back or handle client commands if needed
                await websocket.send_json({"type": "pong", "message": "Connection alive"})
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(websocket)

@app.get("/status")
async def get_status():
    """Get connection status"""
    return {
        "active_connections": len(manager.active_connections),
        "binance_connected": manager.is_connected
    }

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    await manager.stop_binance_connection()

if __name__ == "__main__":
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        log_level="info"
    )