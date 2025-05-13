import pytest
from wayback_archiver import WaybackArchiver
import responses
import requests

def test_url_validation():
    archiver = WaybackArchiver("https://example.com")
    
    # Test valid URLs
    assert archiver._is_valid_url("https://example.com/page")
    assert archiver._is_valid_url("https://sub.example.com/path?q=1")
    
    # Test invalid URLs
    assert not archiver._is_valid_url("javascript:alert(1)")
    assert not archiver._is_valid_url("data:text/html,<script>")
    assert not archiver._is_valid_url("http://localhost")
    assert not archiver._is_valid_url("https://192.168.1.1")

@responses.activate
def test_archive_url_retry():
    # Mock responses for testing retry logic
    responses.add(responses.POST, "https://web.archive.org/save",
                 json={"error": "Rate limited"}, status=429)
    responses.add(responses.POST, "https://web.archive.org/save",
                 json={"success": True}, status=200)
    
    archiver = WaybackArchiver("https://example.com", delay=1)
    assert archiver._archive_url("https://example.com/test")
