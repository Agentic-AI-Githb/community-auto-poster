def generate_social_post(api_key: str, headline: str, link: str) -> str:
    """
    Use OpenRouter to create a short, engaging social media post.
    Automatically selects a free model from OpenRouter's available models.
    """
    # --- 1. Get a free model ID ---
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
        model_id = free_models[0]  # use the first free model
        logger.info("Using free model: %s", model_id)
    except requests.exceptions.RequestException as err:
        logger.error("Failed to fetch models: %s", err)
        if err.response is not None:
            logger.error("Response: %s", err.response.text)
        sys.exit(1)

    # --- 2. Generate the post ---
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    prompt = (
        "Write a short, engaging social media post about the following news headline. "
        "The post should be catchy, under 280 characters, and suitable for a general audience. "
        "Do not use hashtags unless necessary. Include the URL naturally if possible.\n\n"
        f"Headline: {headline}\n"
        f"URL: {link}\n\n"
        "Return only the post text."
    )
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.7,
    }
    logger.info("Generating social post via OpenRouter with model %s...", model_id)
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        if 'choices' in result and len(result['choices']) > 0:
            text = result['choices'][0]['message']['content'].strip()
            logger.info("Generated post: %s", text)
            return text
        logger.error("Unexpected OpenRouter response: %s", result)
        sys.exit(1)
    except requests.exceptions.RequestException as err:
        logger.error("OpenRouter API request failed: %s", err)
        if err.response is not None:
            logger.error("Response: %s", err.response.text)
        sys.exit(1)
