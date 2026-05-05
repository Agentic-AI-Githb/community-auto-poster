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
        "You are a tech journalist. Write a single, concise, engaging social media post (max 250 characters) in plain English about the following AI/tech headline. "
        "Make it sound like exciting news for an AI enthusiast community. "
        "Do NOT use emojis. Only output the final post text, nothing else.\n\n"
        f"Headline: {headline}\n"
        f"URL: {link}"
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
