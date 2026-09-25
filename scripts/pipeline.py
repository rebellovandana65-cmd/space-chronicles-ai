import os
import sys
import json
import asyncio
import subprocess
import requests
from pathlib import Path
from mutagen.mp3 import MP3
import edge_tts

WORKSPACE = Path("output")
WORKSPACE.mkdir(exist_ok=True)
CLIPS_DIR = WORKSPACE / "clips"
CLIPS_DIR.mkdir(exist_ok=True)

def generate_storyboard(prompt: str) -> dict:
    print(f"[*] Planning script for: '{prompt}'...")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    # Try models in order: 2.0-flash, 1.5-flash
    for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        prompt_instruction = (
            f"You are a science documentary director. Write an engaging 4-scene 'What If' space script for: '{prompt}'.\n"
            "Return ONLY raw JSON (no markdown formatting, no ```json tags) with this exact schema:\n"
            "{\n"
            '  "title": "Video Title",\n'
            '  "scenes": [\n'
            '    {"scene_id": 1, "narration": "2 sentences describing the event.", "search_query": "Black Hole"},\n'
            '    {"scene_id": 2, "narration": "2 sentences describing consequences.", "search_query": "Jupiter"},\n'
            '    {"scene_id": 3, "narration": "2 sentences on cosmic impact.", "search_query": "Supernova"},\n'
            '    {"scene_id": 4, "narration": "2 concluding sentences.", "search_query": "Earth"}\n'
            "  ]\n"
            "}"
        )
        
        payload = {
            "contents": [{"parts": [{"text": prompt_instruction}]}],
            "generationConfig": {"temperature": 0.7}
        }
        
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("\n", 1)[-1].rsplit("\n", 1)[0]
                return json.loads(raw_text)
            else:
                print(f"[!] {model_name} returned status {res.status_code}: {res.text[:150]}")
        except Exception as e:
            print(f"[!] Error calling {model_name}: {e}")

    # Built-in fallback so the pipeline never crashes
    print("[*] Using fallback space documentary script...")
    return {
        "title": prompt,
        "scenes": [
            {
                "scene_id": 1,
                "narration": f"What would truly happen if {prompt.lower()}? Space is governed by unforgiving gravitational laws.",
                "search_query": "Galaxy"
            },
            {
                "scene_id": 2,
                "narration": "Planetary orbits would destabilize rapidly as massive tidal forces warp the fabric of space-time.",
                "search_query": "Black Hole"
            },
            {
                "scene_id": 3,
                "narration": "Extreme cosmic radiation would flood the inner system, ionizing atmospheres across surrounding worlds.",
                "search_query": "Supernova"
            },
            {
                "scene_id": 4,
                "narration": "In the end, our solar system would be forever altered into an unrecognizable cosmic graveyard.",
                "search_query": "Earth"
            }
        ]
    }

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
        
        for item in items[:5]:
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
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What if a rogue black hole entered our solar system?"
    storyboard = generate_storyboard(prompt)
    print(f"[*] Title: {storyboard['title']}")
    
    rendered_clips = []
    for scene in storyboard["scenes"]:
        s_id = scene["scene_id"]
        print(f"[*] Building Scene {s_id}...")
        image_path = fetch_nasa_image(scene["search_query"], s_id)
        audio_path = await generate_narration(scene["narration"], s_id)
        clip_path = render_scene(image_path, audio_path, s_id)
        rendered_clips.append(clip_path)

    final_video = WORKSPACE / "final_space_video.mp4"
    concatenate_clips(rendered_clips, final_video)
    print(f"[SUCCESS] Finished video created: {final_video}")

if __name__ == "__main__":
    asyncio.run(main())
    
