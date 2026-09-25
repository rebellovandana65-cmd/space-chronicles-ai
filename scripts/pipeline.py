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

# 1. 3-Minute Comprehensive Documentary Director
def generate_storyboard(prompt: str) -> dict:
    print(f"[*] Director Planning 3-Minute Documentary: '{prompt}'...")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    
    # 8 to 10 comprehensive scenes totaling ~180 seconds
    for model_name in ["gemini-2.0-flash", "gemini-1.5-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        prompt_instruction = (
            f"You are a top-tier science documentary director like BBC or Aperture. "
            f"Write a gripping, educational 3-minute script on: '{prompt}'.\n"
            "Create exactly 8 detailed chronological scenes.\n"
            "Each scene must have 3 to 4 dense, educational, dramatic sentences (~20-25 seconds of speech).\n"
            "Return ONLY raw JSON with this exact schema (no markdown, no backticks):\n"
            "{\n"
            '  "title": "Documentary Title",\n'
            '  "scenes": [\n'
            '    {"scene_id": 1, "narration": "...", "search_query": "deep space nebula"},\n'
            '    {"scene_id": 2, "narration": "...", "search_query": "black hole accretion"},\n'
            '    {"scene_id": 3, "narration": "...", "search_query": "supernova explosion"},\n'
            '    {"scene_id": 4, "narration": "...", "search_query": "solar system planets"},\n'
            '    {"scene_id": 5, "narration": "...", "search_query": "jupiter storm"},\n'
            '    {"scene_id": 6, "narration": "...", "search_query": "galaxy collision"},\n'
            '    {"scene_id": 7, "narration": "...", "search_query": "neutron star pulsar"},\n'
            '    {"scene_id": 8, "narration": "...", "search_query": "earth orbit horizon"}\n'
            "  ]\n"
            "}"
        )
        
        payload = {
            "contents": [{"parts": [{"text": prompt_instruction}]}],
            "generationConfig": {"temperature": 0.7}
        }
        
        try:
            res = requests.post(url, headers=headers, json=payload, timeout=25)
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if raw_text.startswith("```"):
                    raw_text = raw_text.split("\n", 1)[-1].rsplit("\n", 1)[0]
                return json.loads(raw_text)
        except Exception:
            pass

    # Built-in 8-scene 3-minute fail-safe script
    return {
        "title": prompt,
        "scenes": [
            {"scene_id": 1, "narration": f"Across the boundless expanse of space, phenomena exist that challenge every rule of physics. When considering {prompt.lower()}, scientists uncover truths stranger than fiction. The cosmos is not a silent sanctuary, but a violent, evolving tapestry of light and gravity.", "search_query": "deep space galaxy"},
            {"scene_id": 2, "narration": "Centuries of orbital balance can unravel in a mere cosmic blink. When immense gravitational anomalies interact with stellar systems, the sheer curvature of spacetime warps planetary trajectories beyond recognition.", "search_query": "black hole accretion"},
            {"scene_id": 3, "narration": "Tidal disruption forces stretch solid celestial bodies into elongated strands of cosmic debris. Immense friction ignites surrounding gases into blinding accretion disks that emit intense streams of deadly radiation.", "search_query": "supernova remnant"},
            {"scene_id": 4, "narration": "Planets caught in the crossfire experience catastrophic planetary stress. Internal tectonic friction boils mantle layers, creating global volcanic hellscapes that strip away delicate atmospheric shields within hours.", "search_query": "solar flare sun"},
            {"scene_id": 5, "narration": "Gas giants like Jupiter, long acting as protective gravity shields for inner planets, are themselves destabilized. Their massive magnetic belts warp, discharging devastating electromagnetic shockwaves across space.", "search_query": "jupiter storm"},
            {"scene_id": 6, "narration": "Yet, in this chaotic destruction lies the genesis of new cosmic architecture. Matter is not destroyed; it is superheated, condensed, and recycled into the foundational dust of future stellar nurseries.", "search_query": "orion nebula"},
            {"scene_id": 7, "narration": "Modern space telescopes like James Webb have demonstrated that our corner of the universe is surprisingly rare. A fragile oasis protected by delicate orbital mechanics in an unforgiving universe.", "search_query": "deep space telescope"},
            {"scene_id": 8, "narration": "Looking back at our pale blue dot from deep orbit, the lesson is clear. The universe does not negotiate, and our survival relies on understanding the colossal forces that govern reality.", "search_query": "earth orbit horizon"}
        ]
    }

# 2. NASA High-Definition Video & Motion Visual Fetcher
def fetch_nasa_motion_asset(query: str, scene_id: int) -> tuple[Path, str]:
    """Fetches real NASA MP4 video clips when available; falls back to 4K photography."""
    vid_dest = CLIPS_DIR / f"raw_clip_{scene_id:02d}.mp4"
    img_dest = CLIPS_DIR / f"raw_image_{scene_id:02d}.jpg"
    fallback_dest = CLIPS_DIR / f"fallback_{scene_id:02d}.mp4"

    def make_fallback():
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=0x070913:s=1920x1080:d=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(fallback_dest)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return fallback_dest, "video"

    # Step A: Try fetching real NASA MP4 video
    try:
        url_vid = f"[https://images-api.nasa.gov/search?q=](https://images-api.nasa.gov/search?q=){query}&media_type=video"
        res_vid = requests.get(url_vid, timeout=12).json()
        items = res_vid.get("collection", {}).get("items", [])
        if items:
            collection_url = items[0].get("href")
            if collection_url:
                files = requests.get(collection_url, timeout=12).json()
                mp4_urls = [f for f in files if f.endswith("~orig.mp4") or f.endswith("~medium.mp4") or f.endswith(".mp4")]
                if mp4_urls:
                    # Pick a 1080p / medium sized mp4
                    chosen_url = mp4_urls[0]
                    v_data = requests.get(chosen_url, timeout=30, stream=True)
                    with open(vid_dest, "wb") as f:
                        for chunk in v_data.iter_content(chunk_size=1024*1024):
                            f.write(chunk)
                    return vid_dest, "video"
    except Exception as e:
        print(f"[!] NASA Video query failed for '{query}': {e}")

    # Step B: Fallback to high-res image
    try:
        url_img = f"[https://images-api.nasa.gov/search?q=](https://images-api.nasa.gov/search?q=){query}&media_type=image"
        res_img = requests.get(url_img, timeout=12).json()
        items_img = res_img.get("collection", {}).get("items", [])
        for item in items_img[:3]:
            href = item.get("links", [{}])[0].get("href")
            if href:
                i_data = requests.get(href, timeout=20).content
                with open(img_dest, "wb") as f:
                    f.write(i_data)
                return img_dest, "image"
    except Exception:
        pass

    return make_fallback()

# 3. Neural Voice Generation (Documentary Narrator)
async def generate_narration(text: str, scene_id: int) -> Path:
    audio_path = CLIPS_DIR / f"audio_{scene_id:02d}.mp3"
    communicate = edge_tts.Communicate(text, voice="en-US-ChristopherNeural", rate="+2%", pitch="-1Hz")
    await communicate.save(str(audio_path))
    return audio_path

# 4. Dynamic Word-by-Word Subtitle Generator
def create_high_retention_subtitles(text: str, duration: float, srt_path: Path):
    """Chunks text into 3-4 word punchy captions for viewer retention."""
    words = text.split()
    chunk_size = 4
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    chunk_duration = duration / max(1, len(chunks))
    
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, chunk in enumerate(chunks):
            start = idx * chunk_duration
            end = (idx + 1) * chunk_duration
            
            s_h, s_m, s_s = int(start // 3600), int((start % 3600) // 60), start % 60
            e_h, e_m, e_s = int(end // 3600), int((end % 3600) // 60), end % 60
            
            f.write(f"{idx + 1}\n")
            f.write(f"{s_h:02d}:{s_m:02d}:{s_s:06.3f}".replace('.', ',') + " --> " +
                    f"{e_h:02d}:{e_m:02d}:{e_s:06.3f}".replace('.', ',') + "\n")
            f.write(f"{chunk.upper()}\n\n")

# 5. Scene Render: Loops Video or Pans Image to Match Exact Narration Length
def render_scene(asset_path: Path, asset_type: str, audio_path: Path, narration_text: str, scene_id: int) -> Path:
    output_clip = CLIPS_DIR / f"rendered_{scene_id:02d}.mp4"
    srt_path = CLIPS_DIR / f"sub_{scene_id:02d}.srt"
    
    audio_info = MP3(audio_path)
    duration = max(3.5, audio_info.info.length + 0.4)
    create_high_retention_subtitles(narration_text, duration, srt_path)
    
    srt_clean = str(srt_path).replace("\\", "/").replace(":", "\\:")
    sub_filter = (
        f"subtitles='{srt_clean}':force_style='Fontname=Arial Black,FontSize=20,Bold=1,"
        f"PrimaryColour=&H0000FFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2.5,"
        f"Shadow=0,Alignment=2,MarginV=50'"
    )

    if asset_type == "video":
        # Loop real NASA footage smoothly to narration length and scale to 1080p
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", str(asset_path),
            "-i", str(audio_path),
            "-filter_complex",
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,"
            f"{sub_filter},"
            f"fade=t=in:st=0:d=0.4,fade=t=out:st={duration-0.4}:d=0.4,format=yuv420p[v]",
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(duration),
            str(output_clip)
        ]
    else:
        # 4K Smooth dynamic zoom for still photos
        frames = int(duration * 30)
        zoom_expr = "min(zoom+0.0018,1.25)" if scene_id % 2 == 0 else "max(1.25-0.0018*on,1.0)"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(asset_path),
            "-i", str(audio_path),
            "-filter_complex",
            f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            f"zoompan=z='{zoom_expr}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,"
            f"{sub_filter},"
            f"fade=t=in:st=0:d=0.4,fade=t=out:st={duration-0.4}:d=0.4,format=yuv420p[v]",
            "-map", "[v]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(duration),
            str(output_clip)
        ]

    subprocess.run(cmd, check=True)
    return output_clip

# 6. Assembly & Audio Mastering Engine
def assemble_and_master(clip_paths: list[Path], output_path: Path):
    print("[*] Assembling full 3-minute timeline and mastering audio...")
    raw_video = WORKSPACE / "raw_stitched.mp4"
    concat_list = WORKSPACE / "concat_list.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(raw_video)], check=True)

    # Mastered Cosmic Ambient Soundtrack (Sub-bass rumble + deep atmospheric filter)
    cmd_audio = [
        "ffmpeg", "-y",
        "-i", str(raw_video),
        "-f", "lavfi", "-i", "anoisesrc=c=pink:r=44100:a=0.012",
        "-f", "lavfi", "-i", "sine=f=50:r=44100",
        "-filter_complex",
        "[2:a]volume=0.05[sub];[1:a][sub]amix=inputs=2[bed];[0:a][bed]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path)
    ]
    subprocess.run(cmd_audio, check=True)

async def main():
    prompt = sys.argv[1] if len(sys.argv) > 1 else "What if a rogue black hole entered our solar system?"
    storyboard = generate_storyboard(prompt)
    print(f"[*] Title: {storyboard['title']}")
    
    rendered_clips = []
    for scene in storyboard["scenes"]:
        s_id = scene["scene_id"]
        print(f"\n[*] Processing Scene {s_id}/8: query='{scene['search_query']}'")
        asset_path, asset_type = fetch_nasa_motion_asset(scene["search_query"], s_id)
        audio_path = await generate_narration(scene["narration"], s_id)
        
        print(f"[*] Rendering Scene {s_id} ({asset_type}) with dynamic captions...")
        clip_path = render_scene(asset_path, asset_type, audio_path, scene["narration"], s_id)
        rendered_clips.append(clip_path)

    final_video = WORKSPACE / "final_space_video.mp4"
    assemble_and_master(rendered_clips, final_video)
    print(f"\n[SUCCESS] 3-Minute Documentary Ready: {final_video}")

if __name__ == "__main__":
    asyncio.run(main())
    
