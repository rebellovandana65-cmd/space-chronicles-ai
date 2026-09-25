import os
import sys
import json
import asyncio
import subprocess
import requests
from pathlib import Path
from mutagen.mp3 import MP3
import edge_tts
from google import genai
from google.genai import types

WORKSPACE = Path("output")
WORKSPACE.mkdir(exist_ok=True)
CLIPS_DIR = WORKSPACE / "clips"
CLIPS_DIR.mkdir(exist_ok=True)

def generate_storyboard(prompt: str) -> dict:
    print(f"[*] Planning script for: '{prompt}'...")
    client = genai.Client()

    system_instruction = (
        "You are an elite science documentary writer. "
        "Create an engaging 'What If' space script broken into 4 to 6 scenes. "
        "For each scene provide: "
        "1) 'narration': 2 to 3 sentences of dramatic commentary. "
        "2) 'search_query': a 1-to-2 word term to fetch NASA images (e.g., 'Jupiter', 'Supernova', 'Earth', 'Nebula')."
    )

    # Use the stable production flash model
    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=f"Topic: {prompt}",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "scenes": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "scene_id": {"type": "INTEGER"},
                                "narration": {"type": "STRING"},
                                "search_query": {"type": "STRING"}
                            },
                            "required": ["scene_id", "narration", "search_query"]
                        }
                    }
                },
                "required": ["title", "scenes"]
            },
            temperature=0.7
        )
    )
    return json.loads(response.text)

def fetch_nasa_image(query: str, scene_id: int) -> Path:
    dest_path = CLIPS_DIR / f"image_{scene_id:02d}.jpg"
    fallback_path = CLIPS_DIR / f"fallback_{scene_id:02d}.jpg"

    def create_fallback():
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=0x050510:s=1920x1080:d=1",
            "-vframes", "1", str(fallback_path)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return fallback_path

    try:
        url = f"https://images-api.nasa.gov/search?q={query}&media_type=image"
        res = requests.get(url, timeout=15).json()
        items = res.get("collection", {}).get("items", [])
        
        if not items:
            return create_fallback()

        for item in items[:3]:
            href = item.get("links", [{}])[0].get("href")
            if href:
                img_data = requests.get(href, timeout=20).content
                with open(dest_path, "wb") as f:
                    f.write(img_data)
                return dest_path
    except Exception as e:
        print(f"[!] NASA warning: {e}")
    
    return create_fallback()

async def generate_narration(text: str, scene_id: int) -> Path:
    audio_path = CLIPS_DIR / f"audio_{scene_id:02d}.mp3"
    communicate = edge_tts.Communicate(text, voice="en-US-ChristopherNeural")
    await communicate.save(str(audio_path))
    return audio_path

def render_scene(image_path: Path, audio_path: Path, scene_id: int) -> Path:
    output_clip = CLIPS_DIR / f"rendered_{scene_id:02d}.mp4"
    audio_info = MP3(audio_path)
    duration = max(3.0, audio_info.info.length + 0.5)
    frames = int(duration * 30)

    zoom_expr = "min(zoom+0.0015,1.25)" if scene_id % 2 == 0 else "max(1.25-0.0015*on,1.0)"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-filter_complex",
        f"[0:v]scale=8000:-1,zoompan=z='{zoom_expr}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,"
        f"format=yuv420p[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(duration),
        str(output_clip)
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_clip

def concatenate_clips(clip_paths: list[Path], output_path: Path):
    concat_list = WORKSPACE / "concat_list.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path)
    ]
    subprocess.run(cmd, check=True)

async def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What if a black hole passed Earth?"
    storyboard = generate_storyboard(prompt)
    
    rendered_clips = []
    for scene in storyboard["scenes"]:
        s_id = scene["scene_id"]
        image_path = fetch_nasa_image(scene["search_query"], s_id)
        audio_path = await generate_narration(scene["narration"], s_id)
        clip_path = render_scene(image_path, audio_path, s_id)
        rendered_clips.append(clip_path)

    final_video = WORKSPACE / "final_space_video.mp4"
    concatenate_clips(rendered_clips, final_video)
    print(f"[SUCCESS] Finished video created: {final_video}")

if __name__ == "__main__":
    asyncio.run(main())
    
