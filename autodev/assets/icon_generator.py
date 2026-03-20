"""App icon generation using DALL-E 3 and Pillow for resizing.

Flow:
1. Build an icon-design prompt using Claude (describe style, colours, etc.).
2. Call the OpenAI DALL-E 3 API via httpx to generate a 1024x1024 icon.
3. Save the master icon and use Pillow to produce every required size for
   Android (mdpi through xxxhdpi) and iOS.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from PIL import Image  # type: ignore[import-untyped]

from autodev.config import get_settings

logger = logging.getLogger(__name__)

# Android launcher icon sizes (folder -> px).
ANDROID_ICON_SIZES: Dict[str, int] = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}

# iOS icon sizes (filename -> px).
IOS_ICON_SIZES: Dict[str, int] = {
    "Icon-App-20x20@1x.png": 20,
    "Icon-App-20x20@2x.png": 40,
    "Icon-App-20x20@3x.png": 60,
    "Icon-App-29x29@1x.png": 29,
    "Icon-App-29x29@2x.png": 58,
    "Icon-App-29x29@3x.png": 87,
    "Icon-App-40x40@1x.png": 40,
    "Icon-App-40x40@2x.png": 80,
    "Icon-App-40x40@3x.png": 120,
    "Icon-App-60x60@2x.png": 120,
    "Icon-App-60x60@3x.png": 180,
    "Icon-App-76x76@1x.png": 76,
    "Icon-App-76x76@2x.png": 152,
    "Icon-App-83.5x83.5@2x.png": 167,
    "Icon-App-1024x1024@1x.png": 1024,
}

_DALLE_API_URL = "https://api.openai.com/v1/images/generations"
_DALLE_TIMEOUT = 120


@dataclass
class IconSet:
    """Paths to all generated icon assets."""

    master_icon: str = ""
    android_icons: Dict[str, str] = field(default_factory=dict)
    ios_icons: Dict[str, str] = field(default_factory=dict)


class IconGenerator:
    """Generate app icons via DALL-E 3 and resize for all platforms."""

    def __init__(
        self,
        openai_api_key: Optional[str] = None,
        claude_api_key: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._openai_key = openai_api_key or settings.dalle_api_key
        self._claude_key = claude_api_key or settings.claude_api_key
        self._claude_model = settings.claude_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        app_name: str,
        description: str,
        output_dir: str,
    ) -> IconSet:
        """Generate a full icon set for *app_name*.

        Parameters
        ----------
        app_name:
            Human-readable application name.
        description:
            Short description of the app's purpose.
        output_dir:
            Root directory where ``android/`` and ``ios/`` icon folders
            will be created.

        Returns
        -------
        IconSet
            Paths to all generated icon files.
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Step 1: build an icon prompt via Claude.
        prompt = await self._build_icon_prompt(app_name, description)
        logger.info("Icon prompt: %s", prompt[:200])

        # Step 2: generate the master 1024x1024 icon via DALL-E 3.
        master_bytes = await self._call_dalle(prompt)
        master_path = out / "icon_master_1024.png"
        master_path.write_bytes(master_bytes)
        logger.info("Master icon saved to %s", master_path)

        # Step 3: resize for all platforms.
        icon_set = IconSet(master_icon=str(master_path))
        master_image = Image.open(io.BytesIO(master_bytes)).convert("RGBA")

        icon_set.android_icons = self._resize_android(master_image, out)
        icon_set.ios_icons = self._resize_ios(master_image, out)

        return icon_set

    # ------------------------------------------------------------------
    # Prompt generation via Claude
    # ------------------------------------------------------------------

    async def _build_icon_prompt(
        self, app_name: str, description: str
    ) -> str:
        """Use Claude to craft a DALL-E prompt for the icon."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._claude_key)

        system = (
            "You are an expert mobile app icon designer. Given an app name "
            "and description, produce a single DALL-E image-generation prompt "
            "for a flat-design, modern app icon. The icon must: be a simple, "
            "clean vector-style illustration; use a vibrant gradient "
            "background; have a single recognizable symbol in the centre; "
            "have NO text or letters; look professional on a phone home "
            "screen. Reply ONLY with the prompt text, nothing else."
        )

        message = await client.messages.create(
            model=self._claude_model,
            max_tokens=300,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"App name: {app_name}\n"
                        f"Description: {description}\n\n"
                        "Generate the DALL-E prompt:"
                    ),
                }
            ],
        )

        return message.content[0].text.strip()

    # ------------------------------------------------------------------
    # DALL-E 3 API call
    # ------------------------------------------------------------------

    async def _call_dalle(self, prompt: str) -> bytes:
        """Call OpenAI DALL-E 3 and return raw PNG bytes."""
        headers = {
            "Authorization": f"Bearer {self._openai_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
            "response_format": "b64_json",
            "quality": "standard",
        }

        async with httpx.AsyncClient(timeout=_DALLE_TIMEOUT) as client:
            response = await client.post(
                _DALLE_API_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        data = response.json()["data"][0]
        return base64.b64decode(data["b64_json"])

    # ------------------------------------------------------------------
    # Resizing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resize_android(
        master: Image.Image, out: Path
    ) -> Dict[str, str]:
        """Create Android launcher icons for every density bucket."""
        results: Dict[str, str] = {}
        android_dir = out / "android"

        for folder, size in ANDROID_ICON_SIZES.items():
            dest = android_dir / folder
            dest.mkdir(parents=True, exist_ok=True)
            icon_path = dest / "ic_launcher.png"
            resized = master.resize((size, size), Image.LANCZOS)
            resized.save(str(icon_path), "PNG")
            results[folder] = str(icon_path)
            logger.debug(
                "Android icon %s -> %s (%dpx)", folder, icon_path, size
            )

        return results

    @staticmethod
    def _resize_ios(
        master: Image.Image, out: Path
    ) -> Dict[str, str]:
        """Create iOS icon assets in all required sizes."""
        results: Dict[str, str] = {}
        ios_dir = out / "ios" / "AppIcon.appiconset"
        ios_dir.mkdir(parents=True, exist_ok=True)

        for filename, size in IOS_ICON_SIZES.items():
            icon_path = ios_dir / filename
            resized = master.resize((size, size), Image.LANCZOS)
            resized.save(str(icon_path), "PNG")
            results[filename] = str(icon_path)
            logger.debug("iOS icon %s (%dpx)", filename, size)

        # Write a minimal Contents.json for Xcode.
        contents_json = _build_ios_contents_json()
        (ios_dir / "Contents.json").write_text(
            contents_json, encoding="utf-8"
        )

        return results


def _build_ios_contents_json() -> str:
    """Generate the Xcode asset catalog Contents.json for app icons."""
    images: List[dict] = []
    entries = [
        ("20x20", "1x", "iphone", "Icon-App-20x20@1x.png"),
        ("20x20", "2x", "iphone", "Icon-App-20x20@2x.png"),
        ("20x20", "3x", "iphone", "Icon-App-20x20@3x.png"),
        ("29x29", "1x", "iphone", "Icon-App-29x29@1x.png"),
        ("29x29", "2x", "iphone", "Icon-App-29x29@2x.png"),
        ("29x29", "3x", "iphone", "Icon-App-29x29@3x.png"),
        ("40x40", "1x", "iphone", "Icon-App-40x40@1x.png"),
        ("40x40", "2x", "iphone", "Icon-App-40x40@2x.png"),
        ("40x40", "3x", "iphone", "Icon-App-40x40@3x.png"),
        ("60x60", "2x", "iphone", "Icon-App-60x60@2x.png"),
        ("60x60", "3x", "iphone", "Icon-App-60x60@3x.png"),
        ("76x76", "1x", "ipad", "Icon-App-76x76@1x.png"),
        ("76x76", "2x", "ipad", "Icon-App-76x76@2x.png"),
        ("83.5x83.5", "2x", "ipad", "Icon-App-83.5x83.5@2x.png"),
        ("1024x1024", "1x", "ios-marketing", "Icon-App-1024x1024@1x.png"),
    ]

    for size, scale, idiom, filename in entries:
        images.append(
            {
                "size": size,
                "idiom": idiom,
                "filename": filename,
                "scale": scale,
            }
        )

    return json.dumps(
        {"images": images, "info": {"version": 1, "author": "autodev"}},
        indent=2,
    )
