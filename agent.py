#!/usr/bin/env python3
"""
phpFox v4 AI Agent – Fetches RSS headline, creates a social post with OpenRouter,
and publishes it to your phpFox feed using OAuth2.
"""

import os
import sys
import logging
import requests
import feedparser

# ----------------------------------------------------------------------
# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Environment variables (all required except RSS_FEED_URL)
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
PHPFOX_CLIENT_ID = os.environ.get('PHPFOX_CLIENT_ID')
PHPFOX_CLIENT_SECRET = os.environ.get('PHPFOX_CLIENT_SECRET')
PHPFOX_URL = os.environ.get('PHPFOX_URL', '').rstrip('/')   # no trailing slash
PHPFOX_USER_ID = os.environ.get('PHPFOX_USER_ID')           # must be an integer
RSS_FEED_URL = os.environ.get(
    'RSS_FEED_URL',
    'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml'
)
# Validate mandatory variables
MANDATORY = {
    'OPENROUTER_API_KEY': OPENROUTER_API_KEY,
    'PHPFOX_CLIENT_ID': PHPFOX_CLIENT_ID,
    'PHPFOX_CLIENT_SECRET': PHPFOX_CLIENT_SECRET,
    'PHPFOX_URL': PHPFOX_URL,
    'PHPFOX_USER_ID': PHPFOX_USER_ID,
}
missing = [k for k, v in MANDATORY.items() if not v]
if missing:
    logger.error("Missing environment variables: %s", ', '.join(missing))
    sys.exit(1)

try:
    PHPFOX_USER_ID = int(PHPFOX_USER_ID)
except ValueError:
    logger.error("PHPFOX_USER_ID must be an integer")
    sys.exit(1)

# ----------------------------------------------------------------------
def get_access_token(client_id: str, client_secret: str, base_url: str) -> str:
    """Obtain OAuth2 access token from phpFox v4."""
    token_url = f"{base_url}/restful_api/oauth/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret,
    }
    logger.info("Requesting access token from %s", token_url)
    try:
        resp = requests.post(token_url, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if 'access_token' in data:
            logger.info("Access token obtained successfully")
            return data['access_token']
        logger.error("Token response missing access_token: %s", data)
        sys.exit(1)
    except requests.exceptions.RequestException as err:
        logger.error("Failed to obtain access token: %s", err)
        if err.response is not None:
            logger.error("Response body: %s", err.response.text)
        sys.exit(1)

# ----------------------------------------------------------------------
def fetch_latest_headline(feed_url: str):
    """Return (title, link) of the latest RSS entry."""
    logger.info("Fetching RSS feed: %s", feed_url)
    feed = feedparser.parse(feed_url)
    if feed.bozo and not feed.entries:
        logger.error("RSS parse error: %s", feed.bozo_exception)
        sys.exit(1)
    if not feed.entries:
        logger.error("No entries found in RSS feed")
        sys.exit(1)
    entry = feed.entries[0]
    title = entry.title
    link = entry.link
    logger.info("Latest headline: %s", title)
    return title, link

# ----------------------------------------------------------------------
def generate_social_post(api_key: str, headline: str, link: str) -> str:
    """
    Use OpenRouter to create a short, engaging social media post.
    Tries all available free models until one succeeds.
    """
    # --- 1. Get all free model IDs ---
    logger.info("Fetching available free models from OpenRouter...")
    models_url = "https://openrouter.ai/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = requests.get(models_url, headers=headers, timeout=15)
        resp.raise_for_status()
        models_data = resp.json()
        free_models = [
            m['id'] for m in models_data.get('data', [])
            if ':free' in m.get('id', '')
        ]
        if not free_models:
            logger.error("No free models found in OpenRouter response")
            sys.exit(1)
        logger.info("Found %d free models", len(free_models))
    except requests.exceptions.RequestException as err:
        logger.error("Failed to fetch models: %s", err)
        if err.response is not None:
            logger.error("Response: %s", err.response.text)
        sys.exit(1)

    # --- 2. Try each free model until one gives a post ---
    url = "https://openrouter.ai/api/v1/chat/completions"
    prompt = (
        "Write a short, engaging social media post about the following news headline. "
        "The post should be catchy, under 280 characters, and suitable for a general audience. "
        "Do not use hashtags unless necessary. Include the URL naturally if possible.\n\n"
        f"Headline: {headline}\n"
        f"URL: {link}\n\n"
        "Return only the post text."
    )

    for model_id in free_models:
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.7,
        }
        logger.info("Trying model: %s", model_id)
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            result = resp.json()
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message'].get('content')
                if content and content.strip():
                    text = content.strip()
                    logger.info("Generated post with model %s: %s", model_id, text)
                    return text
                else:
                    logger.warning("Model %s returned empty content, trying next...", model_id)
            else:
                logger.warning("Unexpected response from model %s: %s", model_id, result)
        except requests.exceptions.RequestException as err:
            logger.warning("Model %s request failed: %s, trying next...", model_id, err)

    logger.error("All free models failed to generate a valid post")
    sys.exit(1)

# ----------------------------------------------------------------------
def post_to_phpfox(base_url: str, access_token: str,
                   user_id: int, content: str) -> bool:
    """Post a status feed to phpFox v4."""
    post_url = f"{base_url}/restful_api/feed"
    headers = {"Authorization": f"Bearer {access_token}"}
    payload = {
        "user_id": user_id,
        "content": content,
        "privacy": 0,          # 0 = public
    }
    logger.info("Posting to phpFox feed as user %d", user_id)
    try:
        resp = requests.post(post_url, data=payload, headers=headers, timeout=30)
        if resp.status_code in (200, 201, 204):
            logger.info("Feed posted successfully")
            return True
        logger.error("Feed post failed (status %s): %s", resp.status_code, resp.text)
        return False
    except requests.exceptions.RequestException as err:
        logger.error("Request error posting feed: %s", err)
        return False

# ----------------------------------------------------------------------
def main():
    logger.info("Starting AI Agent for phpFox v4")
    # 1. Fetch latest headline
    headline, link = fetch_latest_headline(RSS_FEED_URL)

    # 2. Generate social post
    social_post = generate_social_post(OPENROUTER_API_KEY, headline, link)

    # 3. Obtain OAuth2 token
    token = get_access_token(PHPFOX_CLIENT_ID, PHPFOX_CLIENT_SECRET, PHPFOX_URL)

    # 4. Post to phpFox
    if not post_to_phpfox(PHPFOX_URL, token, PHPFOX_USER_ID, social_post):
        sys.exit(1)

    logger.info("Agent completed successfully")

if __name__ == '__main__':
    main()
