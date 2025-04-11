# Wayback Archiver

A Python tool to automatically crawl and archive entire subdomains in the Internet Archive's Wayback Machine.

## Overview

Wayback Archiver helps preserve web content by crawling all pages within a specified subdomain and submitting them to the Internet Archive's Wayback Machine. This is particularly useful for:

- Preserving content from websites that might be shut down
- Creating complete historical snapshots of blogs or documentation sites
- Ensuring important information remains available even if the original site changes
- Archiving personal projects, portfolios, or academic websites

## Features

- **User-friendly Web Interface**: Easy-to-use UI for configuring and monitoring archiving jobs
- **Recursive Crawling**: Automatically discovers and follows links within the target subdomain
- **Smart Filtering**: Excludes common paths that would result in duplicate content (like tag pages, categories, etc.)
- **Configurable Parameters**:
  - Control crawl depth with max pages limit
  - Set delays between requests for API politeness
  - Custom exclude patterns for site-specific requirements
  - HTTPS-only mode (enabled by default)
- **Batch Processing**: Handles large sites by processing URLs in batches with configurable pauses
- **Resilient Operation**:
  - Retry mechanism with exponential backoff for failed archive attempts
  - Ability to resume archiving from previously failed URLs
  - Robots.txt respect for ethical crawling
- **Detailed Logging**: Comprehensive logs and output files to track progress and results

## Screenshot

![Wayback Archiver Web Interface](https://github.com/nickheynen/wayback-archiver/raw/main/screenshots/web_interface.png)

## Requirements

- Python 3.7+
- Required packages:
  - `requests`: For HTTP operations
  - `beautifulsoup4`: For HTML parsing
  - `flask`: For the web interface

## Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/nickheynen/wayback-archiver.git
   cd wayback-archiver
   ```

2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Web Interface

1. Start the application by running the `web_interface.py` script:
   ```bash
   python3 web_interface.py
   ```

2. Open your browser and navigate to `http://127.0.0.1:5000`.

3. Fill out the form with your target subdomain and configuration options.

4. Click "Start Archiving" and monitor the progress.

## Command Line Usage

You can run the archiver directly from the command line:

```bash
python3 wayback_archiver.py https://example.com --email your-email@example.com --delay 15 --max-pages 500
```

### Authentication Options

#### Email Authentication (Recommended for Basic Use)
```bash
python3 wayback_archiver.py https://example.com --email your-email@example.com
```

#### S3 Authentication (For Internet Archive Contributors)
```bash
python3 wayback_archiver.py https://example.com --s3-access-key YOUR_ACCESS_KEY --s3-secret-key YOUR_SECRET_KEY
```

### HTTPS and Protocol Options

By default, the tool only archives HTTPS URLs. To include HTTP URLs:
```bash
python3 wayback_archiver.py https://example.com --include-http
```

### Robots.txt Control

By default, the tool respects robots.txt. To override:
```bash
python3 wayback_archiver.py https://example.com --ignore-robots-txt
```

For all available options:
```bash
python3 wayback_archiver.py --help
```

## Online Deployment

The web interface can be deployed online using various hosting services. Here's how to deploy on:

### Using PythonAnywhere

1. Create a free account on [PythonAnywhere](https://www.pythonanywhere.com/)
2. Upload the project files or clone the repository
3. Set up a web app with Flask
4. Configure your WSGI file to point to the `web_interface.py` application

### Using Heroku

1. Add a `Procfile` with the content:
   ```
   web: gunicorn web_interface:app
   ```
2. Add `gunicorn` to your requirements.txt
3. Deploy to Heroku

## Output Files

- **Log File**: `wayback_archiver.log` contains detailed logs of the archiving process.
- **Successful URLs**: Saved to a JSON file named `successful_urls_<domain>_<timestamp>.json`.
- **Failed URLs**: Saved to a JSON file named `failed_urls_<domain>_<timestamp>.json`.

## API Usage Notice

This tool uses the Internet Archive's Wayback Machine API. Please use it responsibly:

- Set reasonable delays between requests (the default is 15 seconds)
- Provide your email or S3 authentication when archiving
- Use S3 authentication if you're a frequent contributor (contact Internet Archive for credentials)
- Keep HTTPS-only mode enabled when possible for better web security
- Respect robots.txt directives (enabled by default)
- Respect the terms of service of both the Internet Archive and target websites
- Consider donating to the Internet Archive if you find this tool valuable

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a new branch for your feature
3. Add your changes
4. Submit a pull request

For bugs, questions, or feature requests, please open an issue on GitHub.