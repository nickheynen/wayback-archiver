# Wayback Archiver

A Python tool to automatically crawl and archive entire subdomains in the Internet Archive's Wayback Machine.

## Overview

Wayback Archiver helps preserve web content by crawling all pages within a specified subdomain and submitting them to the Internet Archive's Wayback Machine. This is particularly useful for:

- Preserving content from websites that might be shut down
- Creating complete historical snapshots of blogs or documentation sites
- Ensuring important information remains available even if the original site changes

## Features

- Fully local web interface for ease of use
- Recursive crawling of all pages within a subdomain
- Smart filtering to avoid archiving duplicate or irrelevant content (e.g., tags, categories, etc.)
- Polite API usage with configurable delays between requests
- Batch processing to manage large sites
- Retry mechanism with exponential backoff for failed archive attempts
- Detailed logging of the archiving process
- Ability to retry previously failed URLs

## Requirements

- Python 3.7+
- Required packages:
  - `requests`
  - `beautifulsoup4`
  - `flask`

## Installation

1. Clone or download this repository.
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Running the Web Interface

1. Start the application by running the `web_interface.py` script:

   ```bash
   python web_interface.py
   ```

2. Open your browser and navigate to `http://127.0.0.1:5000`.

3. Fill out the form and start the archiving process.

## Usage

The web interface allows you to:
- Input the subdomain to archive.
- Configure optional parameters like email, delay, max pages, and exclude patterns.
- Monitor the progress of the archiving process in real-time.

## Output

- **Log File**: `wayback_archiver.log` contains detailed logs of the archiving process.
- **Successful URLs**: Saved to a JSON file named `successful_urls_<domain>_<timestamp>.json`.
- **Failed URLs**: Saved to a JSON file named `failed_urls_<domain>_<timestamp>.json`.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.