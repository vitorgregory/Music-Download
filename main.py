from app import app
import os

if __name__ == '__main__':
    # No Docker, 0.0.0.0 é obrigatório
    # Run in production mode by default (disable Flask debug mode)
    app.run(host="0.0.0.0", port=5000, debug=False)