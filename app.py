import websocket
import json
import threading

def on_message(ws, message):
    data = json.loads(message)
    if 'stream' in data:
        # you can pipeline this data to your function, analysis or backtesting
        print(f"Symbol: {data['data']['s']}, Price: {data['data']['c']}, Time: {data['data']['E']}")
    else:
        print(f"Received message: {message}")

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"WebSocket connection closed: {close_status_code} - {close_msg}")

def on_open(ws):
    print("WebSocket connection opened")
    # Subscribe to the ticker stream for BTCUSDT
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": ["btcusdt@ticker"],
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

def on_ping(ws, message):
    print(f"Received ping: {message}")
    ws.send(message, websocket.ABNF.OPCODE_PONG)
    print(f"Sent pong: {message}")

if __name__ == "__main__":
    websocket.enableTrace(True)
    socket = 'wss://stream.binance.com:9443/ws'
    ws = websocket.WebSocketApp(socket,
                                on_message=on_message,
                                on_error=on_error,
                                on_close=on_close,
                                on_open=on_open,
                                on_ping=on_ping)