"""OpenAI helpers for mirror copy (text + image generation)."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Optional

from openai import AsyncOpenAI

from config import (
    DEFAULT_OPENAI_MODEL,
    OPEN_AI_KEY,
    OPENAI_FREQUENCY_PENALTY,
    OPENAI_IMAGE_FALLBACK_MODELS,
    OPENAI_IMAGE_MODEL,
    OPENAI_IMAGE_QUALITY,
    OPENAI_IMAGE_SIZE,
    OPENAI_MAX_COMPLETION_TOKENS,
    OPENAI_PRESENCE_PENALTY,
    OPENAI_RETRIES,
    OPENAI_SEED,
    OPENAI_TEMPERATURE,
    OPENAI_TIMEOUT,
    OPENAI_TOP_P,
)

logger = logging.getLogger(__name__)

DEFAULT_MEDIA_STYLE_PROMPT = """Create images for news and current events. Style guidelines:
- Clean, professional look; suitable for news and editorial use.
- Prefer clear composition: one main subject or idea per image.
- Use realistic or semi-realistic style; avoid cartoon or fantasy unless the news topic clearly suggests it.
- For maps or locations: simple, readable layout; neutral colors; no decorative clutter.
- Good contrast and readability; avoid overly dark or noisy backgrounds.
- Neutral, informative tone; no sensational or dramatic exaggeration.
- Output image prompts in English, max 30 words, descriptive and concrete."""


def _is_openai_invalid_image_model_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "does not exist" in text
        or ("invalid_value" in text and "model" in text)
        or "model_not_found" in text
    )


def _is_openai_unknown_param_error(exc: BaseException, param: str) -> bool:
    text = str(exc).lower()
    return "unknown parameter" in text and param.lower() in text


def _build_openai_image_kwargs(
    model: str, prompt: str, size: str, quality: Optional[str]
) -> dict:
    """Параметри images.generate під конкретну модель (як у ReposterBot)."""
    model_l = (model or "dall-e-3").strip().lower()
    kwargs: dict = {"model": model, "prompt": prompt, "n": 1}

    if model_l.startswith("dall-e-3"):
        allowed_sizes = {"1024x1024", "1792x1024", "1024x1792"}
        if size in ("1536x1024", "1792x1024"):
            kwargs["size"] = "1792x1024"
        elif size in ("1024x1536", "1024x1792"):
            kwargs["size"] = "1024x1792"
        else:
            kwargs["size"] = size if size in allowed_sizes else "1024x1024"
        if quality:
            q = quality.lower()
            if q in ("high", "hd"):
                kwargs["quality"] = "hd"
            elif q in ("medium", "standard", "low", "auto"):
                kwargs["quality"] = "standard"
    elif model_l.startswith("dall-e-2"):
        allowed_sizes = {"256x256", "512x512", "1024x1024"}
        kwargs["size"] = size if size in allowed_sizes else "1024x1024"
    else:
        allowed_sizes = {"1024x1024", "1536x1024", "1024x1536", "auto"}
        kwargs["size"] = size if size in allowed_sizes else "1024x1024"
        if quality:
            q = quality.lower()
            if q in ("low", "medium", "high", "auto"):
                kwargs["quality"] = q
            elif q == "hd":
                kwargs["quality"] = "high"
            elif q == "standard":
                kwargs["quality"] = "medium"

    return kwargs


_async_client: AsyncOpenAI | None = None
_async_client_key: str | None = None


def get_async_openai(api_key: str | None = None) -> AsyncOpenAI:
    global _async_client, _async_client_key
    key = api_key or OPEN_AI_KEY
    if _async_client is None or _async_client_key != key:
        _async_client = AsyncOpenAI(api_key=key)
        _async_client_key = key
    return _async_client


def _image_models_to_try(primary: str) -> list[str]:
    primary = (primary or OPENAI_IMAGE_MODEL or "gpt-image-2.6-flare").strip()
    models = [primary]
    for fallback in OPENAI_IMAGE_FALLBACK_MODELS or ():
        if fallback and fallback not in models:
            models.append(fallback)
    return models


class Ai:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or OPEN_AI_KEY
        self.async_openai_client = get_async_openai(self.api_key)

    async def async_get_response(
        self, prompt: str, system_message: str = None
    ) -> str:
        if not system_message:
            return "Помилка API"

        last_exception = None
        for attempt in range(OPENAI_RETRIES):
            try:
                response = await self.async_openai_client.chat.completions.create(
                    model=DEFAULT_OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=OPENAI_MAX_COMPLETION_TOKENS,
                    temperature=OPENAI_TEMPERATURE,
                    top_p=OPENAI_TOP_P,
                    frequency_penalty=OPENAI_FREQUENCY_PENALTY,
                    presence_penalty=OPENAI_PRESENCE_PENALTY,
                    seed=OPENAI_SEED,
                    timeout=OPENAI_TIMEOUT,
                )
                return response.choices[0].message.content
            except Exception as e:
                last_exception = e
                if attempt < OPENAI_RETRIES - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    logger.exception(
                        "OpenAI async_get_response failed: %s", last_exception
                    )
        return "Помилка API"

    async def generate_image_from_news(
        self,
        news_text: str,
        folder_id: Optional[int] = None,
        donor_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        style_prompt: Optional[str] = None,
    ) -> bytes:
        """Генерація зображення через OpenAI images.generate (як у ReposterBot)."""
        _ = (folder_id, donor_id, channel_id)
        style_source = (style_prompt or "").strip() or DEFAULT_MEDIA_STYLE_PROMPT
        system_content = (
            "Style and context for the image (follow these guidelines):\n"
            f"{style_source}\n\n"
            "You are a helpful assistant that creates concise image generation prompts. "
            "Based on the news and the style above, write ONE short descriptive English "
            "prompt for AI image generation. Max 30 words. Output only the prompt, no explanation."
        )
        prompt_instruction = (
            "Based on this news, write ONE short descriptive English prompt for AI "
            f"image generation. Max 30 words. News: {news_text}"
        )
        prompt_response = await self.async_openai_client.chat.completions.create(
            model=DEFAULT_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt_instruction},
            ],
            max_tokens=100,
            temperature=OPENAI_TEMPERATURE,
            top_p=OPENAI_TOP_P,
            frequency_penalty=OPENAI_FREQUENCY_PENALTY,
            presence_penalty=OPENAI_PRESENCE_PENALTY,
            seed=OPENAI_SEED,
            timeout=OPENAI_TIMEOUT,
        )
        clean_prompt = (prompt_response.choices[0].message.content or "").strip()
        if not clean_prompt:
            raise RuntimeError("OpenAI повернув порожній image prompt")

        logger.info("OpenAI image prompt: %s", clean_prompt[:200])

        result = None
        models_to_try = _image_models_to_try(OPENAI_IMAGE_MODEL)
        last_image_err: Optional[Exception] = None
        for idx, image_model in enumerate(models_to_try):
            try:
                image_kwargs = _build_openai_image_kwargs(
                    image_model,
                    clean_prompt,
                    OPENAI_IMAGE_SIZE,
                    OPENAI_IMAGE_QUALITY,
                )
                logger.info(
                    "images.generate model=%s size=%s",
                    image_model,
                    image_kwargs.get("size"),
                )
                try:
                    result = await self.async_openai_client.images.generate(
                        **image_kwargs
                    )
                except Exception as openai_img_err:
                    if "response_format" in image_kwargs and _is_openai_unknown_param_error(
                        openai_img_err, "response_format"
                    ):
                        image_kwargs.pop("response_format", None)
                        result = await self.async_openai_client.images.generate(
                            **image_kwargs
                        )
                    else:
                        raise openai_img_err
                break
            except Exception as openai_img_err:
                last_image_err = openai_img_err
                if (
                    _is_openai_invalid_image_model_error(openai_img_err)
                    and idx < len(models_to_try) - 1
                ):
                    logger.warning(
                        "Image model %s unavailable, trying %s",
                        image_model,
                        models_to_try[idx + 1],
                    )
                    continue
                raise

        if result is None and last_image_err is not None:
            raise last_image_err
        if not result or not result.data:
            raise RuntimeError("OpenAI не повернув зображення")

        item = result.data[0]
        b64_data = getattr(item, "b64_json", None)
        if b64_data:
            return base64.b64decode(b64_data)

        image_url = getattr(item, "url", None)
        if not image_url:
            raise RuntimeError("OpenAI не повернув ні b64_json, ні url зображення")

        import httpx

        async with httpx.AsyncClient(timeout=60.0) as client:
            img_response = await client.get(image_url)
            if img_response.status_code != 200:
                raise RuntimeError(
                    f"Помилка завантаження зображення OpenAI: {img_response.status_code}"
                )
            return img_response.content
