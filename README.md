# Wayback Archiver

A Python tool to automatically crawl and archive entire subdomains in the Internet Archive's Wayback Machine.

## Overview

Wayback Archiver helps preserve web content by crawling all pages within a specified subdomain and submitting them to the Internet Archive's Wayback Machine. This is particularly useful for:

- Preserving content from websites that might be shut down
- Creating complete historical snapshots of blogs or documentation sites
- Ensuring important information remains available even if the original site changes

## Features

- Recursive crawling of all pages within a subdomain
- Smart filtering to avoid archiving duplicate content (tags, categories, etc.)
- Polite API usage with configurable delays between requests
- Batch processing to manage large sites
- Retry mechanism with exponential backoff for failed archive attempts
- Detailed logging of the archiving process
- Ability to retry previously failed URLs

## Requirements

- Python 3.6+
- Required packages:
  - requests
  - beautifulsoup4
  - urllib3

## Installation

1. Clone or download this repository
2. Install the required packages:

```
pip install requests beautifulsoup4
```

## Usage

### Basic Usage

```
python wayback-archiver.py https://blog.example.com
```

### With Email (Recommended)

```
python wayback-archiver.py https://blog.example.com --email your.email@example.com
```

Providing your email is recommended for API attribution and necessary for high-volume archiving.

### Full Options

```
python wayback-archiver.py [-h] [--email EMAIL] [--delay DELAY] [--max-pages MAX_PAGES]
                          [--max-retries MAX_RETRIES] [--backoff-factor BACKOFF_FACTOR]
                          [--batch-size BATCH_SIZE] [--batch-pause BATCH_PAUSE]
                          [--exclude EXCLUDE [EXCLUDE ...]] [--retry-file RETRY_FILE]
                          subdomain
```

## Arguments

| Argument | Description |
|----------|-------------|
| `subdomain` | The subdomain to archive (e.g., https://blog.example.com) |
| `--email` | Your email address (recommended for API use) |
| `--delay` | Delay between archive requests in seconds (default: 30) |
| `--max-pages` | Maximum number of pages to crawl (default: unlimited) |
| `--max-retries` | Maximum retry attempts for failed archives (default: 3) |
| `--backoff-factor` | Exponential backoff factor for retries (default: 2.0) |
| `--batch-size` | Process URLs in batches of this size (default: 100) |
| `--batch-pause` | Seconds to pause between batches (default: 300) |
| `--exclude` | URL patterns to exclude (default includes common WordPress paths) |
| `--retry-file` | JSON file containing previously failed URLs to retry |

## Examples

### Archive a blog with 1-minute delays and maximum 500 pages

```
python wayback-archiver.py https://blog.example.com --email your.email@example.com --delay 60 --max-pages 500
```

### Exclude specific URL patterns

```
python wayback-archiver.py https://blog.example.com --exclude /downloads/ /members/ /premium/
```

### Retry failed URLs from a previous run

```
python wayback-archiver.py https://blog.example.com --retry-file failed_urls_blog_example_com_20250401_120000.json
```

## How It Works

1. The tool crawls the specified subdomain to discover all URLs
2. It filters out URLs based on the exclude patterns
3. It submits each discovered URL to the Wayback Machine's "Save Page Now" API
4. For failed submissions, it implements a retry mechanism with exponential backoff
5. Failed URLs after all retries are saved to a JSON file for future retry attempts

## API Usage Notes

This tool uses the Internet Archive's Wayback Machine API. Please be respectful of their service:

- Use reasonable delays between requests (default is 30 seconds)
- Provide your email for attribution
- Respect the batch pauses for large sites

## Troubleshooting

### Common Issues

- **Rate limiting (429 errors)**: Increase the --delay parameter
- **Connection errors**: Check your internet connection or increase retries
- **Failed URLs**: Use the generated JSON file with --retry-file to retry later

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.