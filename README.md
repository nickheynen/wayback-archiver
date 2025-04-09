# Wayback Archiver

A beginner-friendly tool to save websites to the Internet Archive's Wayback Machine.

## What is This?

The Wayback Archiver helps you save websites to the Internet Archive (archive.org) so they'll be preserved forever, even if the original site disappears. Think of it as taking snapshots of websites and storing them in a digital time capsule.

## Why Use This Tool?

- **Save websites that might disappear** - perfect for preserving blogs, news sites, or documentation
- **Create a permanent record** of important information
- **Help future researchers** access today's web content

## Getting Started (Step-by-Step)

### First-Time Setup

1. **Make sure Python is installed**
   - You need Python 3.7 or newer
   - Not sure if you have Python? Open Terminal/Command Prompt and type: `python --version` or `python3 --version`

2. **Install the required packages**
   - Open Terminal/Command Prompt
   - Navigate to the wayback-archiver folder
   - Run this command:
   ```
   pip install requests beautifulsoup4 flask
   ```

### Running the Tool

1. **Start the web interface**
   - Open Terminal/Command Prompt
   - Navigate to the wayback-archiver folder
   - Run this command:
   ```
   python web_interface.py
   ```
   - You should see a message saying the server started

2. **Access the tool in your browser**
   - Open any web browser (Chrome, Firefox, Safari, etc.)
   - Type this address: `http://127.0.0.1:5000`
   - You should now see the Wayback Archiver interface

3. **Archive a website**
   - Enter the website address you want to archive (e.g., `https://example.com`)
   - Optional: Enter your email address (recommended but not required)
   - Click the "Start Archiving" button
   - Wait for the process to complete (this may take several minutes)

### Understanding the Results

After archiving completes, you'll get:

- **Log file**: A detailed record of what happened
- **Success file**: A list of all pages successfully archived
- **Failed file**: Any pages that couldn't be archived (if any)

These files will be saved in the same folder as the tool.

## Common Questions

**How long does archiving take?**
It depends on the size of the site. A small site might take minutes, while a large site could take hours.

**Is there a limit to how many pages I can archive?**
The tool itself has no limits, but the Internet Archive may have rate limits. The tool automatically uses delays to stay within these limits.

**Do I need to provide my email address?**
It's recommended but not required. Including your email helps the Internet Archive contact you if there are any issues.

**What if the archiving process gets interrupted?**
You can always restart it. The tool creates files of failed URLs that you can retry later.

## Getting Help

If you run into problems or have questions, please check the GitHub issues page or open a new issue describing your problem.

## License

This project is available under the MIT License, meaning it's free to use, modify, and share.