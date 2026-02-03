from flask import Flask
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, generate_csrf

app = Flask(__name__)

# Basic secret key for CSRF and session signing. Override in production.
# Determine persistent secret key path
secret_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'secret.key')
env_secret = os.environ.get('SECRET_KEY')
if env_secret:
	app.config['SECRET_KEY'] = env_secret
else:
	# Try to load a persisted secret key, otherwise generate and persist one.
	try:
		os.makedirs(os.path.dirname(secret_path), exist_ok=True)
		if os.path.exists(secret_path):
			with open(secret_path, 'rb') as f:
				app.config['SECRET_KEY'] = f.read().strip().decode('utf-8')
		else:
			# Generate a secure random key and persist it for future restarts
			import secrets
			key = secrets.token_urlsafe(48)
			with open(secret_path, 'w') as f:
				f.write(key)
			app.config['SECRET_KEY'] = key
	except Exception:
		# Fallback to an ephemeral dev key if filesystem unavailable
		app.config.setdefault('SECRET_KEY', 'dev-secret')

# Rate limiting (basic)
storage = os.environ.get('RATELIMIT_STORAGE_URL')
try:
	# Attempt to initialise Limiter with configured storage (e.g. redis)
	limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"], storage_uri=storage)
	limiter.init_app(app)
except Exception as e:
	# Fall back to in-memory storage if redis client is missing or misconfigured.
	# In-memory storage is not suitable for distributed deployments but allows
	# the app to start cleanly when Redis or required client libs are absent.
	import warnings
	warnings.warn(f"Failed to initialize rate limiter storage ({e}); falling back to in-memory storage.")
	limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"]) 
	limiter.init_app(app)

# Expose `csrf_token()` in templates
app.jinja_env.globals['csrf_token'] = generate_csrf

# CSRF protection for forms
csrf = CSRFProtect(app)

# Import routes after app is created
from . import routes
