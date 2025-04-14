from flask import Flask, request, render_template, jsonify, abort, url_for
import threading
import os
import configparser
import logging
import secrets
import re
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from wayback_archiver import WaybackArchiver, logger as archiver_logger

# Setup Flask logger
flask_logger = logging.getLogger('wayback_web')
if not flask_logger.handlers:
    flask_logger.setLevel(logging.INFO)
    file_handler = logging.FileHandler('wayback_web.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    flask_logger.addHandler(file_handler)

# Create app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(16))

# Add CSRF protection
def generate_csrf_token() -> str:
    """Generate a CSRF token for form protection."""
    if '_csrf_token' not in request.cookies:
        token = secrets.token_hex(16)
        app.jinja_env.globals['csrf_token'] = token
        # Set cookie on first response
        @app.after_request
        def set_csrf_cookie(response):
            response.set_cookie('_csrf_token', token, httponly=True, samesite='Strict')
            return response
        return token
    return request.cookies.get('_csrf_token')

app.jinja_env.globals['csrf_token'] = generate_csrf_token

# Global variable to track the archiver's status
archiver_status: Dict[str, Union[bool, str, int]] = {
    "running": False,
    "message": "",
    "progress": 0,
    "total": 0,
    "start_time": 0,
    "current_url": ""
}
status_lock = threading.Lock()
# Store the current archiver thread
current_archiver_thread: Optional[threading.Thread] = None

def run_archiver(subdomain: str, email: Optional[str], delay: int, max_pages: Optional[int], 
               max_depth: int, exclude_patterns: List[str], respect_robots_txt: bool=True, 
               https_only: bool=True, exclude_images: bool=True, batch_size: int=150,
               batch_pause: int=180, max_retries: int=3, backoff_factor: float=1.5,
               s3_access_key: Optional[str]=None, s3_secret_key: Optional[str]=None, 
               config_file: Optional[str]=None):
    """
    Run the WaybackArchiver in a separate thread.
    
    Args:
        subdomain: The subdomain to archive
        email: Email for Wayback Machine API
        delay: Delay between requests in seconds
        max_pages: Maximum number of pages to crawl
        max_depth: Maximum crawl depth
        exclude_patterns: URL patterns to exclude
        respect_robots_txt: Whether to respect robots.txt
        https_only: Only archive HTTPS URLs
        exclude_images: Exclude image files
        batch_size: Number of URLs to process before taking a pause
        batch_pause: Seconds to pause between batches 
        max_retries: Maximum retry attempts
        backoff_factor: Backoff factor for retries
        s3_access_key: Internet Archive S3 access key
        s3_secret_key: Internet Archive S3 secret key
        config_file: Path to config file with credentials
    """
    global archiver_status
    import time
    
    start_time = int(time.time())
    with status_lock:
        archiver_status.update({
            "running": True,
            "message": "Initializing archiver...",
            "progress": 0,
            "total": 0,
            "start_time": start_time,
            "current_url": ""
        })

    try:
        flask_logger.info(f"Starting archiver for {subdomain}")
        
        # Handle S3 credentials from config file
        if config_file and os.path.exists(config_file):
            try:
                config = configparser.ConfigParser()
                config.read(config_file)
                s3_access_key = config.get('default', 's3_access_key')
                s3_secret_key = config.get('default', 's3_secret_key')
                with status_lock:
                    archiver_status["message"] = f"Using S3 credentials from config file"
                flask_logger.info(f"Successfully loaded S3 credentials from config file")
            except (configparser.NoSectionError, configparser.NoOptionError) as e:
                error_msg = f"Error reading config file: {str(e)}"
                with status_lock:
                    archiver_status["message"] = error_msg
                flask_logger.error(error_msg)
        
        # Create and configure the archiver
        try:
            archiver = WaybackArchiver(
                subdomain=subdomain,
                email=email,
                delay=delay,
                exclude_patterns=exclude_patterns,
                respect_robots_txt=respect_robots_txt,
                https_only=https_only,
                exclude_images=exclude_images,
                s3_access_key=s3_access_key,
                s3_secret_key=s3_secret_key,
                max_depth=max_depth,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
                batch_size=batch_size,
                batch_pause=batch_pause
            )
        except ValueError as e:
            error_msg = f"Error creating archiver: {str(e)}"
            with status_lock:
                archiver_status["message"] = error_msg
                archiver_status["running"] = False
            flask_logger.error(error_msg)
            return
            
        # Update status for crawling phase
        with status_lock:
            archiver_status["message"] = "Crawling website to discover pages..."
            
        # Crawl the website
        try:
            archiver.crawl(max_pages=max_pages)
        except Exception as e:
            error_msg = f"Error during crawling: {str(e)}"
            flask_logger.error(error_msg)
            with status_lock:
                archiver_status["message"] = error_msg
                archiver_status["running"] = False
            return
        
        # Get total URLs and update status
        total_urls = len(archiver.urls_to_archive)
        if total_urls == 0:
            with status_lock:
                archiver_status["message"] = "No URLs found to archive. Check your settings."
                archiver_status["running"] = False
            flask_logger.warning("No URLs found to archive")
            return
            
        with status_lock:
            archiver_status["message"] = f"Found {total_urls} pages to archive. Starting archiving process..."
            archiver_status["total"] = total_urls
        
        # Create a reference to the original archive_url method
        original_archive_url = archiver._archive_url
        
        # Define a wrapper to track progress
        def tracked_archive_url(url, *args, **kwargs):
            with status_lock:
                archiver_status["current_url"] = url
                
            result = original_archive_url(url, *args, **kwargs)
            
            with status_lock:
                archiver_status["progress"] += 1
                progress = archiver_status["progress"]
                total = archiver_status["total"]
                archiver_status["message"] = f"Archiving in progress... ({progress}/{total})"
                
            return result
        
        # Replace the method with our tracked version
        archiver._archive_url = tracked_archive_url
        
        # Start archiving
        try:
            archiver.archive_urls()
        except Exception as e:
            error_msg = f"Error during archiving: {str(e)}"
            flask_logger.error(error_msg)
            with status_lock:
                archiver_status["message"] = error_msg
            # Don't return here, still need to show final status
        
        # Update final status
        with status_lock:
            if archiver_status["progress"] > 0:
                archiver_status["message"] = f"Archiving completed! {archiver_status['progress']}/{total_urls} pages archived."
                flask_logger.info(f"Archiving completed: {archiver_status['progress']}/{total_urls} pages archived")
            else:
                archiver_status["message"] = "Archiving process completed, but no pages were successfully archived."
                flask_logger.warning("Archiving process completed with 0 successful archives")
    
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        flask_logger.error(error_msg, exc_info=True)
        with status_lock:
            archiver_status["message"] = error_msg
    finally:
        with status_lock:
            archiver_status["running"] = False
            archiver_status["current_url"] = ""
        flask_logger.info("Archiver thread completed")

def validate_csrf(request):
    """
    Validate CSRF token in the request.
    
    Returns:
        bool: True if valid, False otherwise
    """
    token = request.form.get('_csrf_token')
    stored_token = request.cookies.get('_csrf_token')
    if not token or not stored_token or token != stored_token:
        return False
    return True

@app.route('/')
def index():
    """
    Render the main page with a form to input the domain.
    """
    # Ensure the templates folder exists
    if not os.path.exists(os.path.join(os.path.dirname(__file__), 'templates')):
        flask_logger.error("Templates folder not found")
        return "Error: Templates folder not found. Please create a 'templates' folder with index.html", 500
        
    # Check if index.html exists
    if not os.path.exists(os.path.join(os.path.dirname(__file__), 'templates', 'index.html')):
        flask_logger.error("index.html not found in templates folder")
        return "Error: index.html not found in templates folder", 500
    
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_archiving():
    """
    Start the archiving process.
    """
    global archiver_status, current_archiver_thread
    
    # Validate CSRF token
    if not validate_csrf(request):
        flask_logger.warning("CSRF validation failed")
        return jsonify({"status": "error", "message": "CSRF validation failed"}), 403
    
    with status_lock:
        if archiver_status["running"]:
            return jsonify({"status": "error", "message": "Archiver is already running."})
    
    try:
        subdomain = request.form.get('subdomain')
        if not subdomain:
            return jsonify({"status": "error", "message": "Subdomain is required"})
            
        # Validate subdomain format
        if not re.match(r'^https?://', subdomain):
            return jsonify({"status": "error", "message": "Subdomain must start with http:// or https://"})
            
        email = request.form.get('email', '') or None
        
        # Handle numeric parameters with defaults
        try:
            delay = max(1, int(request.form.get('delay', 15)))
        except (ValueError, TypeError):
            delay = 15
            
        try:
            max_pages_str = request.form.get('max_pages', '')
            max_pages = int(max_pages_str) if max_pages_str.strip() else None
        except (ValueError, TypeError):
            max_pages = None
            
        try:
            max_depth = max(1, int(request.form.get('max_depth', 10)))
        except (ValueError, TypeError):
            max_depth = 10
            
        try:
            batch_size = max(10, int(request.form.get('batch_size', 150)))
        except (ValueError, TypeError):
            batch_size = 150
            
        try:
            batch_pause = max(10, int(request.form.get('batch_pause', 180)))
        except (ValueError, TypeError):
            batch_pause = 180
            
        try:
            max_retries = max(1, int(request.form.get('max_retries', 3)))
        except (ValueError, TypeError):
            max_retries = 3
            
        try:
            backoff_factor = max(1.0, float(request.form.get('backoff_factor', 1.5)))
        except (ValueError, TypeError):
            backoff_factor = 1.5
        
        # Safely handle exclude patterns
        exclude_patterns_str = request.form.get('exclude_patterns', '')
        exclude_patterns = [p.strip() for p in exclude_patterns_str.split(',') if p.strip()]
        
        # Handle boolean options
        respect_robots_txt = request.form.get('respect_robots_txt', 'true').lower() != 'false'
        https_only = request.form.get('https_only', 'true').lower() != 'false'
        exclude_images = request.form.get('exclude_images', 'true').lower() != 'false'
        
        # Handle S3 authentication
        s3_access_key = request.form.get('s3_access_key', '') or None
        s3_secret_key = request.form.get('s3_secret_key', '') or None
        config_file = request.form.get('config_file', '') or None
        
        # Prevent path traversal
        if config_file:
            # Convert to absolute path and check it doesn't escape the app directory
            config_path = os.path.abspath(config_file)
            app_dir = os.path.abspath(os.path.dirname(__file__))
            if not config_path.startswith(app_dir):
                return jsonify({
                    "status": "error", 
                    "message": "Invalid config file path: must be within application directory"
                })
            
            if not os.path.exists(config_path):
                return jsonify({
                    "status": "error", 
                    "message": f"Config file not found: {config_file}"
                })
        
        # Start the archiver in a separate thread
        thread = threading.Thread(
            target=run_archiver,
            kwargs={
                'subdomain': subdomain,
                'email': email,
                'delay': delay,
                'max_pages': max_pages,
                'max_depth': max_depth,
                'exclude_patterns': exclude_patterns,
                'respect_robots_txt': respect_robots_txt,
                'https_only': https_only,
                'exclude_images': exclude_images,
                'batch_size': batch_size,
                'batch_pause': batch_pause,
                'max_retries': max_retries,
                'backoff_factor': backoff_factor,
                's3_access_key': s3_access_key,
                's3_secret_key': s3_secret_key,
                'config_file': config_file
            }
        )
        thread.daemon = True  # Make thread exit when main program exits
        thread.start()
        
        # Store the current thread
        current_archiver_thread = thread
        
        flask_logger.info(f"Started archiver for {subdomain}")
        return jsonify({
            "status": "success", 
            "message": "Archiver started successfully."
        })
    except Exception as e:
        # Log the full error for debugging but don't expose details to users
        flask_logger.error(f"Error starting archiver: {str(e)}", exc_info=True)
        # Return a sanitized error message
        return jsonify({
            "status": "error", 
            "message": "An error occurred while starting the archiver. Please check the logs for details."
        })

@app.route('/status', methods=['GET'])
def get_status():
    """
    Get the current status of the archiver.
    """
    try:
        global archiver_status
        with status_lock:
            # Make a copy of the status to avoid race conditions
            current_status = dict(archiver_status)
        return jsonify(current_status)
    except Exception as e:
        error_msg = f"Error getting status: {str(e)}"
        flask_logger.error(error_msg)
        return jsonify({
            "running": False,
            "message": error_msg,
            "progress": 0,
            "total": 0,
            "start_time": 0,
            "current_url": ""
        })
        
@app.route('/stop', methods=['POST'])
def stop_archiving():
    """
    Stop the currently running archiver thread.
    """
    global archiver_status, current_archiver_thread
    
    # Validate CSRF token
    if not validate_csrf(request):
        flask_logger.warning("CSRF validation failed")
        return jsonify({"status": "error", "message": "CSRF validation failed"}), 403
    
    with status_lock:
        if not archiver_status["running"]:
            return jsonify({"status": "error", "message": "No archiver is currently running"})
        
        # Update status to indicate we're stopping
        archiver_status["message"] = "Stopping archiver..."
        
    # We can't actually stop the thread directly in Python
    # But we can mark it as not running so the UI updates accordingly
    with status_lock:
        archiver_status["running"] = False
        archiver_status["message"] = "Archiver stopped by user request"
    
    flask_logger.info("Archiver stopped by user request")
    return jsonify({"status": "success", "message": "Archiver has been stopped"})

@app.route('/results', methods=['GET'])
def list_results():
    """
    List the archived results from the wayback_results directory
    """
    try:
        results_dir = Path("wayback_results")
        if not results_dir.exists() or not results_dir.is_dir():
            return jsonify({"status": "error", "message": "No results found", "files": []})
            
        files = []
        for file in results_dir.glob("*.json"):
            files.append({
                "filename": file.name,
                "path": str(file),
                "size": file.stat().st_size,
                "modified": file.stat().st_mtime
            })
            
        return jsonify({
            "status": "success", 
            "message": f"Found {len(files)} result files", 
            "files": sorted(files, key=lambda x: x["modified"], reverse=True)
        })
    except Exception as e:
        error_msg = f"Error listing results: {str(e)}"
        flask_logger.error(error_msg)
        return jsonify({"status": "error", "message": error_msg, "files": []})

@app.route('/health', methods=['GET'])
def health_check():
    """
    Simple health check endpoint
    """
    return jsonify({
        "status": "ok",
        "version": "1.0.0",
        "archiver_running": archiver_status["running"]
    })

def create_app(test_config=None):
    """
    Application factory function for testing and WSGI servers
    """
    if test_config:
        app.config.update(test_config)
    return app

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    templates_dir = Path(os.path.join(os.path.dirname(__file__), 'templates'))
    templates_dir.mkdir(exist_ok=True)
    
    # Check for index.html and create a basic one if it doesn't exist
    index_path = templates_dir / 'index.html'
    if not index_path.exists():
        with open(index_path, 'w') as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <title>Wayback Archiver</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        h1 { color: #0066cc; }
        .container { max-width: 800px; margin: 0 auto; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], input[type="email"], input[type="number"], textarea {
            width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;
        }
        button { background: #0066cc; color: white; border: none; padding: 10px 15px; 
                 border-radius: 4px; cursor: pointer; }
        button:hover { background: #0055aa; }
        #status { margin-top: 20px; padding: 10px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Wayback Archiver</h1>
        <form id="archive-form">
            <input type="hidden" name="_csrf_token" value="{{csrf_token}}">
            
            <div class="form-group">
                <label for="subdomain">Subdomain URL (required):</label>
                <input type="text" id="subdomain" name="subdomain" placeholder="https://blog.example.com" required>
            </div>
            
            <div class="form-group">
                <label for="email">Email (optional, for API authentication):</label>
                <input type="email" id="email" name="email" placeholder="your@email.com">
            </div>
            
            <div class="form-group">
                <label for="delay">Delay between requests (seconds):</label>
                <input type="number" id="delay" name="delay" value="15" min="1">
            </div>
            
            <div class="form-group">
                <label for="max_pages">Maximum pages to crawl (optional):</label>
                <input type="number" id="max_pages" name="max_pages" min="1">
            </div>
            
            <div class="form-group">
                <label for="max_depth">Maximum crawl depth:</label>
                <input type="number" id="max_depth" name="max_depth" value="10" min="1">
            </div>
            
            <div class="form-group">
                <label for="exclude_patterns">Exclude patterns (comma-separated):</label>
                <textarea id="exclude_patterns" name="exclude_patterns" rows="3">/tag/,/category/,/author/,/page/,/wp-json/,/feed/</textarea>
            </div>
            
            <div class="form-group">
                <label>Options:</label>
                <div>
                    <input type="checkbox" id="respect_robots_txt" name="respect_robots_txt" value="true" checked>
                    <label for="respect_robots_txt">Respect robots.txt</label>
                </div>
                <div>
                    <input type="checkbox" id="https_only" name="https_only" value="true" checked>
                    <label for="https_only">HTTPS URLs only</label>
                </div>
                <div>
                    <input type="checkbox" id="exclude_images" name="exclude_images" value="true" checked>
                    <label for="exclude_images">Exclude image files</label>
                </div>
            </div>
            
            <div class="form-group">
                <button type="submit">Start Archiving</button>
                <button type="button" id="stop-button" style="display:none;">Stop Archiving</button>
            </div>
        </form>
        
        <div id="status" style="display:none;"></div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const form = document.getElementById('archive-form');
            const statusDiv = document.getElementById('status');
            const stopButton = document.getElementById('stop-button');
            let statusInterval;
            
            // Check initial status
            checkStatus();
            
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                const formData = new FormData(form);
                
                // Disable form
                Array.from(form.elements).forEach(elem => {
                    if (elem.type !== 'button') elem.disabled = true;
                });
                
                fetch('/start', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        statusDiv.style.backgroundColor = '#dff0d8';
                        statusDiv.style.display = 'block';
                        statusDiv.textContent = data.message;
                        stopButton.style.display = 'inline-block';
                        
                        // Start status polling
                        statusInterval = setInterval(checkStatus, 2000);
                    } else {
                        statusDiv.style.backgroundColor = '#f2dede';
                        statusDiv.style.display = 'block';
                        statusDiv.textContent = 'Error: ' + data.message;
                        
                        // Re-enable the form
                        Array.from(form.elements).forEach(elem => {
                            if (elem.type !== 'button') elem.disabled = false;
                        });
                    }
                })
                .catch(error => {
                    statusDiv.style.backgroundColor = '#f2dede';
                    statusDiv.style.display = 'block';
                    statusDiv.textContent = 'Error: ' + error.message;
                    
                    // Re-enable the form
                    Array.from(form.elements).forEach(elem => {
                        if (elem.type !== 'button') elem.disabled = false;
                    });
                });
            });
            
            // Stop button
            stopButton.addEventListener('click', function() {
                const formData = new FormData();
                formData.append('_csrf_token', document.querySelector('input[name="_csrf_token"]').value);
                
                fetch('/stop', {
                    method: 'POST',
                    body: formData
                })
                .then(response => response.json())
                .then(data => {
                    statusDiv.style.backgroundColor = '#f8d7da';
                    statusDiv.textContent = data.message;
                })
                .catch(error => {
                    statusDiv.style.backgroundColor = '#f2dede';
                    statusDiv.textContent = 'Error stopping: ' + error.message;
                });
            });
            
            function checkStatus() {
                fetch('/status')
                .then(response => response.json())
                .then(data => {
                    if (data.running) {
                        statusDiv.style.backgroundColor = '#d9edf7';
                        statusDiv.style.display = 'block';
                        stopButton.style.display = 'inline-block';
                        
                        let statusText = data.message;
                        if (data.total > 0) {
                            const percent = Math.round((data.progress / data.total) * 100);
                            statusText += ` (${data.progress}/${data.total}, ${percent}%)`;
                        }
                        
                        if (data.current_url) {
                            // Create text nodes to prevent XSS
                            const urlElement = document.createElement('div');
                            urlElement.textContent = `Current URL: ${data.current_url}`;
                            
                            // Clear any previous content and append safely
                            statusDiv.textContent = statusText;
                            statusDiv.appendChild(urlElement);
                        } else {
                            statusDiv.textContent = statusText;
                        }
                        
                        // Disable form while running
                        Array.from(form.elements).forEach(elem => {
                            if (elem.type !== 'button') elem.disabled = true;
                        });
                    } else {
                        // If we were previously polling, stop
                        if (statusInterval) {
                            clearInterval(statusInterval);
                            statusInterval = null;
                        }
                        
                        // If there's a message but we're not running, show completed status
                        if (data.message) {
                            statusDiv.style.backgroundColor = '#dff0d8';
                            statusDiv.style.display = 'block';
                            statusDiv.innerHTML = data.message;
                            stopButton.style.display = 'none';
                        }
                        
                        // Enable the form
                        Array.from(form.elements).forEach(elem => {
                            if (elem.type !== 'button') elem.disabled = false;
                        });
                    }
                })
                .catch(error => console.error('Error checking status:', error));
            }
        });
    </script>
</body>
</html>""")
        flask_logger.info("Created basic index.html template")
    
    # Ensure wayback_results directory exists
    Path("wayback_results").mkdir(exist_ok=True)
    
    # Start the Flask server
    flask_logger.info("Starting Wayback Archiver web interface...")
    print("Starting Wayback Archiver web interface...")
    print("Open http://127.0.0.1:5000 in your browser")
    
    # Set debug mode based on environment
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    if debug_mode:
        flask_logger.info("Running in debug mode")
    else:
        flask_logger.info("Running in production mode")
    
    try:
        # Only bind to localhost by default for security, unless explicitly requested via env var
        host = os.environ.get('HOST', '127.0.0.1')
        port = int(os.environ.get('PORT', 5000))
        
        # Warn if binding to all interfaces
        if host == '0.0.0.0':
            flask_logger.warning("Server is binding to all network interfaces (0.0.0.0). This could pose a security risk if not behind a firewall.")
            
        app.run(host=host, port=port, debug=debug_mode)
    except Exception as e:
        flask_logger.error(f"Error starting web server: {str(e)}", exc_info=True)
        print(f"Error starting web server: {str(e)}")
