from app import app, socketio
import os

if __name__ == '__main__':
    # No Docker, 0.0.0.0 é obrigatório
    # Run with Socket.IO support for real-time events
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)