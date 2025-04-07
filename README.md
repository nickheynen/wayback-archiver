# Wayback Archiver

A Python tool to automatically crawl and archive entire subdomains in the Internet Archive's Wayback Machine.

## Overview

Wayback Archiver helps preserve web content by crawling all pages within a specified subdomain and submitting them to the Internet Archive's Wayback Machine. This is particularly useful for:

- Preserving content from websites that might be shut down
- Creating complete historical snapshots of blogs or documentation sites
- Ensuring important information remains available even if the original site changes

## Features

- Recursive crawling of all pages within a subdomain
- Smart filtering to avoid archiving duplicate or irrelevant content (e.g., tags, categories, etc.)
- Polite API usage with configurable delays between requests
- Batch processing to manage large sites
- Retry mechanism with exponential backoff for failed archive attempts
- Detailed logging of the archiving process
- Ability to retry previously failed URLs

## Requirements

- Python 3.7+ (updated to match the script's compatibility)
- Required packages:
  - `requests`
  - `beautifulsoup4`

## Installation

1. Clone or download this repository.
2. Install the required packages:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python wayback-archiver.py https://blog.example.com
```

### With Email (Recommended)

```bash
python wayback-archiver.py https://blog.example.com --email your.email@example.com
```

Providing your email is recommended for API attribution and necessary for high-volume archiving.

### Full Options

```bash
python wayback-archiver.py [-h] [--email EMAIL] [--delay DELAY] [--max-pages MAX_PAGES]
                          [--max-retries MAX_RETRIES] [--backoff-factor BACKOFF_FACTOR]
                          [--batch-size BATCH_SIZE] [--batch-pause BATCH_PAUSE]
                          [--exclude EXCLUDE [EXCLUDE ...]] [--retry-file RETRY_FILE]
                          subdomain
```

## Arguments

| Argument              | Description                                                                                     | Default Value |
|-----------------------|-------------------------------------------------------------------------------------------------|---------------|
| `subdomain`           | The subdomain to archive (e.g., `https://blog.example.com`).                                    | Required      |
| `--email`             | Your email address (recommended for API use).                                                  | None          |
| `--delay`             | Delay between archive requests in seconds.                                                     | 30            |
| `--max-pages`         | Maximum number of pages to crawl.                                                              | Unlimited     |
| `--max-retries`       | Maximum retry attempts for failed archives.                                                    | 3             |
| `--backoff-factor`    | Exponential backoff factor for retries.                                                        | 2.0           |
| `--batch-size`        | Number of URLs to process before taking a longer pause.                                        | 100           |
| `--batch-pause`       | Seconds to pause between batches.                                                              | 300           |
| `--exclude`           | URL patterns to exclude (e.g., `/tag/`, `/category/`).                                         | WordPress defaults |
| `--retry-file`        | JSON file containing previously failed URLs to retry.                                          | None          |

## Examples

### Archive a blog with 1-minute delays and maximum 500 pages

```bash
python wayback-archiver.py https://blog.example.com --email your.email@example.com --delay 60 --max-pages 500
```

### Exclude specific URL patterns

```bash
python wayback-archiver.py https://blog.example.com --exclude /downloads/ /members/ /premium/
```

### Retry failed URLs from a previous run

```bash
python wayback-archiver.py https://blog.example.com --retry-file failed_urls_blog_example_com_20250401_120000.json
```

## How It Works

1. The tool crawls the specified subdomain to discover all URLs.
2. It filters out URLs based on the exclude patterns.
3. It submits each discovered URL to the Wayback Machine's "Save Page Now" API.
4. For failed submissions, it implements a retry mechanism with exponential backoff.
5. Failed URLs after all retries are saved to a JSON file for future retry attempts.

## API Usage Notes

This tool uses the Internet Archive's Wayback Machine API. Please be respectful of their service:

- Use reasonable delays between requests (default is 30 seconds).
- Provide your email for attribution.
- Respect the batch pauses for large sites.

## Troubleshooting

### Common Issues

- **Rate limiting (429 errors)**: Increase the `--delay` parameter.
- **Connection errors**: Check your internet connection or increase retries.
- **Failed URLs**: Use the generated JSON file with `--retry-file` to retry later.

## Output

- **Log File**: `wayback_archiver.log` contains detailed logs of the archiving process.
- **Successful URLs**: Saved to a JSON file named `successful_urls_<domain>_<timestamp>.json`.
- **Failed URLs**: Saved to a JSON file named `failed_urls_<domain>_<timestamp>.json`.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.