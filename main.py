from app import app

if __name__ == '__main__':
    # No docker, 0.0.0.0 é essencial
    app.run(host="0.0.0.0", port=5000, debug=True)