"""Generate scenes for Heaven on Earth: The Awakening"""
import os, requests, json
from dotenv import load_dotenv
load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

SCENE_GENERATION_PROMPT = """You are a cinematic video production expert for AI Bible Gospels — a channel revealing the hidden identity of the 12 Tribes of Israel through Scripture, history, and prophecy.

BRAND STYLE:
- Dark, dramatic backgrounds with golden divine light
- Cinematic, reverent, powerful tone
- Photorealistic modern and ancient biblical settings

CHARACTER ETHNICITY RULES (CRITICAL):
- ISRAELITES / HEBREWS (Scenes 1-4): Dark-brown skinned Black men and women, African American complexion, deep melanated skin. Natural 4C tightly coiled hair: locs, braids, twists, afros, or traditional head wraps. Modern clothing (hoodies, jeans, casual wear) — this is 2026, not ancient times.
- NEGATIVE PROMPT for Israelite characters: NOT Caucasian, NOT European, NOT light-skinned, NOT pale, NOT white, NOT mixed race, NOT straight hair, NOT wavy hair
- ALL NATIONS (Scenes 5-6): Once the globe lights up, show ALL races picking up the Bible — Asian, Latino, White, Middle Eastern, Indigenous. Israel starts it, nations join after.
- ANGELS: Dark-brown skinned, same as Israelites

YOUR TASK:
Read the script below and break it into cinematic scenes for video production. Follow the scene breakdown in the script closely.

For each scene, create:
1. **narration**: Use the narration from the script (keep the powerful prose style). Keep each scene's narration between 30-80 words.
2. **imagePrompt**: Extremely detailed visual description for AI image generation. Include character ethnicity per rules above, clothing details, setting, camera angle, atmosphere. End with "photorealistic, cinematic, 8K detail". NEVER include text or words in the image prompt.
3. **motion**: Camera movement description for video animation. Vary angles.
4. **lighting**: Specific dramatic lighting for the scene.

GUIDELINES:
- Follow the 6-scene structure in the script but split longer scenes into 2-3 sub-scenes for better pacing (aim for 12-18 total scenes)
- Create an INTRO scene (cinematic opening) and OUTRO scene (subscribe CTA)
- The golden glow is the central visual motif — make it progressively more intense
- Modern 2026 setting — urban streets, kitchens, subways, NOT ancient
- NEVER put text, words, letters, or titles in image prompts

Return ONLY valid JSON in this exact format:
{
  "scenes": [
    {
      "narration": "...",
      "imagePrompt": "...",
      "motion": "...",
      "lighting": "..."
    }
  ]
}"""

script = open("heaven_script.txt", "r").read()

print("Sending to Claude AI...")
resp = requests.post(
    ANTHROPIC_URL,
    headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
    json={"model": "claude-sonnet-4-20250514", "max_tokens": 16000,
          "messages": [{"role": "user", "content": f"{SCENE_GENERATION_PROMPT}\n\n---\n\nSCRIPT/CONCEPT:\n\n{script}"}]},
    timeout=300,
)
resp.raise_for_status()
content = resp.json()["content"][0]["text"]
if "```json" in content:
    content = content.split("```json")[1].split("```")[0]
elif "```" in content:
    content = content.split("```")[1].split("```")[0]

scenes = json.loads(content.strip())["scenes"]
print(f"\nGenerated {len(scenes)} scenes:\n")
for i, s in enumerate(scenes, 1):
    narr = s["narration"][:80]
    print(f"  Scene {i}: {narr}...")

# Save for pipeline use
with open("heaven_scenes.json", "w") as f:
    json.dump({"scenes": scenes}, f, indent=2)
print(f"\nSaved to heaven_scenes.json")
