# Wayback Archiver

A simple tool to save copies of websites to the Internet Archive's Wayback Machine.

## What Does It Do?

This tool helps you save entire websites to the Wayback Machine. It:

1. Starts at any webpage you specify
2. Finds all the links on that page
3. Follows those links to find more pages on the same site
4. Saves each page to the Wayback Machine

This is useful when you want to:

* Save a website that might be taken down soon
* Create a backup of your blog or personal site
* Preserve important documentation or articles
* Archive a project before it changes

## Quick Start

1. Make sure you have Python 3.8 or newer installed on your computer
2. Download this tool:

   ```bash
   git clone https://github.com/nickheynen/wayback-archiver.git
   cd wayback-archiver
   ```
3. Install the required software:

   ```bash
   pip install -r requirements.txt
   ```
4. Run it (replace the URL with the website you want to save):

   ```bash
   python wayback_archiver.py https://example.com
   ```

## Basic Usage Examples

Save a website, waiting 15 seconds between each page (recommended):

```bash
python wayback_archiver.py https://example.com --delay 15
```

Save only the first 100 pages found:

```bash
python wayback_archiver.py https://example.com --max-pages 100
```

Save pages but skip image files (recommended):

```bash
python wayback_archiver.py https://example.com --exclude-images
```

## Default Settings

When you run the tool without any extra options, these are the default settings:

| Setting | Default Value | Description | Change with |
|----|----|----|----|
| Delay between requests | 15 seconds | Time to wait between saving pages | `--delay 20` |
| Maximum depth | 10 levels | How many clicks deep to follow links | `--max-depth 5` |
| Batch size | 150 pages | Pages to process before taking a longer break | `--batch-size 100` |
| Batch pause | 180 seconds | Length of break between batches | `--batch-pause 300` |
| Maximum retries | 3 times | Times to retry if a page fails | `--max-retries 5` |
| Retry backoff | 1.5x | Multiplier for delay between retries | `--backoff-factor 2` |
| HTTPS only | Yes | Only save HTTPS pages (safer) | `--include-http` |
| Exclude images | Yes | Skip saving image files | `--include-images` |
| Respect robots.txt | Yes | Follow website crawling rules | `--ignore-robots-txt` |
| URL patterns excluded | Common patterns\* | Skip certain types of URLs | `--exclude` |

\*Default excluded patterns:

* `/tag/`, `/category/` - Tag and category pages
* `/author/`, `/page/` - Author and pagination pages
* `/comment-page-`, `/wp-json/` - WordPress system pages
* `/feed/`, `/wp-content/cache/` - Feed and cache files
* `/wp-admin/`, `/search/` - Admin and search pages
* `/login/`, `/register/` - User account pages
* `/signup/`, `/logout/` - User account pages
* `/privacy-policy/` - Standard policy pages
* `/404/`, `/error/` - Error pages

## Advanced Features

### Adding Your Email
It's good practice to include your email when using the Wayback Machine:
```bash
python wayback_archiver.py https://example.com --email your-email@example.com
```

### Controlling How Deep It Goes
The tool will follow links to find pages. You can control how many "clicks" deep it goes:
```bash
python wayback_archiver.py https://example.com --max-depth 5
```

### Processing in Batches
For large sites, the tool can take breaks between groups of pages:
```bash
python wayback_archiver.py https://example.com --batch-size 50 --batch-pause 180
```
This will process 50 pages, then pause for 3 minutes before continuing.

### Retrying Failed Pages
If some pages fail to save, the tool creates a file in the `wayback_results` folder. You can retry these pages:
```bash
python wayback_archiver.py --retry-file wayback_results/failed_urls_example.com_20240220_123456.json
```

## Where to Find the Results

The tool creates several files in a folder called `wayback_results`:
- `successful_urls_[domain]_[timestamp].json` - List of successfully saved pages
- `failed_urls_[domain]_[timestamp].json` - List of pages that failed to save
- `wayback_archiver.log` - Detailed log of what happened during the process

## Common Problems and Solutions

1. **"Too Many Requests" Error**
   - Increase the delay between requests: `--delay 30`
   - Use smaller batch sizes: `--batch-size 50`
   - Add longer pauses between batches: `--batch-pause 300`

2. **"Connection Error" Messages**
   - The site might be blocking rapid requests; try increasing delays
   - Check if the site is accessible in your browser
   - Check your internet connection

3. **Takes Too Long**
   - Limit the number of pages: `--max-pages 500`
   - Reduce how deep it goes: `--max-depth 5`
   - Skip image files (this is actually the default)
   - Focus on specific sections by starting from a subpage

## Important Notes

- Be considerate: Use reasonable delays between requests (15 seconds or more)
- Some websites don't want to be archived - respect their robots.txt rules
- The tool skips certain paths by default (like login pages and search results)
- For best results, start with a small section of a site before trying to archive everything
- The tool works best with static websites and blogs
- Large, dynamic sites with lots of JavaScript might not archive properly

## Need Help?

- Use `python wayback_archiver.py --help` to see all options
- Create an issue on GitHub if you find a bug or need help
- Check the log file (wayback_archiver.log) for detailed information about any problems

## License

This project is free to use under the MIT License.


