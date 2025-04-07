from flask import Flask, request, render_template, jsonify
import threading
from wayback_archiver import WaybackArchiver

app = Flask(__name__)

# Global variable to track the archiver's status
archiver_status = {
    "running": False,
    "message": "",
    "progress": 0,
    "total": 0
}
status_lock = threading.Lock()

def run_archiver(subdomain, email, delay, max_pages, exclude_patterns):
    """
    Run the WaybackArchiver in a separate thread.
    """
    global archiver_status
    with status_lock:
        archiver_status.update({
            "running": True,
            "message": "Crawling and archiving in progress...",
            "progress": 0,
            "total": 0
        })

    try:
        archiver = WaybackArchiver(
            subdomain=subdomain,
            email=email,
            delay=delay,
            exclude_patterns=exclude_patterns
        )
        archiver.crawl(max_pages=max_pages)
        with status_lock:
            archiver_status["total"] = len(archiver.urls_to_archive)
        archiver.archive_urls()
        with status_lock:
            archiver_status["message"] = "Archiving completed successfully!"
    except Exception as e:
        with status_lock:
            archiver_status["message"] = f"Error: {str(e)}"
    finally:
        with status_lock:
            archiver_status["running"] = False

@app.route('/')
def index():
    """
    Render the main page with a form to input the domain.
    """
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_archiving():
    """
    Start the archiving process.
    """
    global archiver_status
    with status_lock:
        if archiver_status["running"]:
            return jsonify({"status": "error", "message": "Archiver is already running."})

    subdomain = request.form.get('subdomain')
    email = request.form.get('email', None)
    delay = int(request.form.get('delay', 30))
    max_pages = int(request.form.get('max_pages', 0)) or None
    exclude_patterns = request.form.get('exclude_patterns', '').split(',')

    # Start the archiver in a separate thread
    thread = threading.Thread(
        target=run_archiver,
        args=(subdomain, email, delay, max_pages, exclude_patterns)
    )
    thread.start()

    return jsonify({"status": "success", "message": "Archiver started."})

@app.route('/status', methods=['GET'])
def get_status():
    """
    Get the current status of the archiver.
    """
    global archiver_status
    with status_lock:
        return jsonify(archiver_status)

if __name__ == '__main__':
    app.run(debug=True)
