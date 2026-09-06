"""Generate a clear French demo voiceover with the Edge speech service.

Only the short SCENES narration strings are submitted. The application database,
profile and credentials are never read. The returned audio is cached locally.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from render import REPO, SCENES


async def generate_all(output: Path, voice: str, rate: str):
    output.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(3)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    async def generate(index, scene):
        payload = dict(provider="microsoft-edge", voice=voice, rate=rate, text=scene["narration"])
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        destination = output / f"{index:02}.wav"
        metadata = output / f"{index:02}.json"
        if (
            destination.exists()
            and metadata.exists()
            and destination.stat().st_size > 5000
            and json.loads(metadata.read_text()).get("cache_key") == digest
        ):
            print(f"AUDIO {index:02}: cached", flush=True)
            return
        temporary = output / f"{index:02}.partial.mp3"
        try:
            async with semaphore:
                speech = edge_tts.Communicate(
                    scene["narration"],
                    voice=voice,
                    rate=rate,
                    connect_timeout=10,
                    receive_timeout=30,
                )
                await speech.save(str(temporary))
            assert temporary.stat().st_size > 1000, "Empty audio response"
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(temporary),
                    "-ar",
                    "48000",
                    "-ac",
                    "1",
                    str(destination),
                ],
                check=True,
            )
            metadata.write_text(
                json.dumps(dict(cache_key=digest, **payload), ensure_ascii=False, indent=2)
            )
            print(f"AUDIO {index:02}: generated", flush=True)
        finally:
            temporary.unlink(missing_ok=True)

    # Establish service availability before dispatching the remaining clips.
    await generate(1, SCENES[0])
    results = await asyncio.gather(
        *(generate(i, scene) for i, scene in enumerate(SCENES[1:], 2)),
        return_exceptions=True,
    )
    errors = [
        (i, type(result).__name__)
        for i, result in enumerate(results, 2)
        if isinstance(result, Exception)
    ]
    if errors:
        raise RuntimeError(f"Failed narration scenes: {errors}")
    print(f"Narration ready: {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO / "output/demo/narration-claire")
    parser.add_argument("--voice", default="fr-FR-DeniseNeural")
    parser.add_argument("--rate", default="+0%")
    args = parser.parse_args()
    asyncio.run(generate_all(args.output.resolve(), args.voice, args.rate))


if __name__ == "__main__":
    main()
