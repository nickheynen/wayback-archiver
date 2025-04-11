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
        # Create and configure the archiver
        archiver = WaybackArchiver(
            subdomain=subdomain,
            email=email,
            delay=delay,
            exclude_patterns=exclude_patterns
        )
        
        # Update status for crawling phase
        with status_lock:
            archiver_status["message"] = "Crawling website to discover pages..."
            
        # Crawl the website
        archiver.crawl(max_pages=max_pages)
        
        # Get total URLs and update status
        total_urls = len(archiver.urls_to_archive)
        with status_lock:
            archiver_status["message"] = f"Found {total_urls} pages to archive. Starting archiving process..."
            archiver_status["total"] = total_urls
        
        # Create a reference to the original archive_url method
        original_archive_url = archiver._archive_url
        
        # Define a wrapper to track progress
        def tracked_archive_url(*args, **kwargs):
            result = original_archive_url(*args, **kwargs)
            with status_lock:
                archiver_status["progress"] += 1
                progress = archiver_status["progress"]
                total = archiver_status["total"]
                archiver_status["message"] = f"Archiving in progress... ({progress}/{total})"
            return result
        
        # Replace the method with our tracked version
        archiver._archive_url = tracked_archive_url
        
        # Start archiving
        archiver.archive_urls()
        
        # Update final status
        with status_lock:
            archiver_status["message"] = f"Archiving completed successfully! {archiver_status['progress']} pages archived."
    
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
    return render_template('index.html')  # Ensure index.html is in the templates folder

@app.route('/start', methods=['POST'])
def start_archiving():
    """
    Start the archiving process.
    """
    global archiver_status
    with status_lock:
        if archiver_status["running"]:
            return jsonify({"status": "error", "message": "Archiver is already running."})
    
    try:
        subdomain = request.form.get('subdomain')
        if not subdomain:
            return jsonify({"status": "error", "message": "Subdomain is required"})
            
        email = request.form.get('email', '') or None
        
        # Handle delay with default
        try:
            delay = int(request.form.get('delay', 30))
            if delay <= 0:
                delay = 30
        except (ValueError, TypeError):
            delay = 30
        
        # Handle max_pages with proper conversion
        try:
            max_pages_str = request.form.get('max_pages', '')
            max_pages = int(max_pages_str) if max_pages_str.strip() else None
        except (ValueError, TypeError):
            max_pages = None
        
        # Safely handle exclude patterns
        exclude_patterns_str = request.form.get('exclude_patterns', '')
        exclude_patterns = [p.strip() for p in exclude_patterns_str.split(',') if p.strip()]
        
        # Start the archiver in a separate thread
        thread = threading.Thread(
            target=run_archiver,
            args=(subdomain, email, delay, max_pages, exclude_patterns)
        )
        thread.start()
        
        return jsonify({"status": "success", "message": "Archiver started."})
    except Exception as e:
        app.logger.error(f"Error starting archiver: {str(e)}")
        return jsonify({"status": "error", "message": f"Error starting archiver: {str(e)}"})

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
        app.logger.error(f"Error getting status: {str(e)}")
        return jsonify({
            "running": False,
            "message": f"Error retrieving status: {str(e)}",
            "progress": 0,
            "total": 0
        })

if __name__ == '__main__':
    # Automatically start the Flask server
    print("Starting Wayback Archiver web interface...")
    app.run(debug=True)
