"""Generate the v8.0 n8n workflow from v7.2 base."""
import json
import copy
from pathlib import Path

BASE = Path(__file__).parent.parent

# Load v7.2 workflow
with open(BASE / "n8n/Biblical-Video-Workflow-v7.2.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

v8 = copy.deepcopy(wf)
v8["name"] = "Biblical Video Workflow v8.0 - Kling AI Motion"

nodes_by_name = {n["name"]: n for n in v8["nodes"]}

# New jsCode for the Enhanced Format node — does FLUX + Kling in a single Code node
new_jscode = r"""// v8.0 — Parse Perplexity + Generate FLUX images + Kling videos + Build template vars
const response = items[0].json.choices[0].message.content;

// ── Field-name-anchored extraction (same as v7.2) ──
function extractScenes(text) {
  const fieldOrder = ['overlaidText', 'voiceOverText', 'imagePrompt', 'motionDescription'];
  const scenes = [];
  let searchFrom = 0;
  function isWS(ch) { return ch === ' ' || ch === '\n' || ch === '\r' || ch === '\t'; }
  while (true) {
    const firstKey = '"' + fieldOrder[0] + '"';
    const sceneStart = text.indexOf(firstKey, searchFrom);
    if (sceneStart === -1) break;
    const scene = {};
    let pos = sceneStart;
    for (let fi = 0; fi < fieldOrder.length; fi++) {
      const fn = fieldOrder[fi];
      const nextFn = fi < fieldOrder.length - 1 ? fieldOrder[fi + 1] : null;
      const keyPat = '"' + fn + '"';
      const keyPos = text.indexOf(keyPat, pos);
      if (keyPos === -1) break;
      const colonPos = text.indexOf(':', keyPos + keyPat.length);
      const openQuotePos = text.indexOf('"', colonPos + 1);
      const vStart = openQuotePos + 1;
      let vEnd;
      if (nextFn) {
        const nextKeyPat = '"' + nextFn + '"';
        const nextKeyPos = text.indexOf(nextKeyPat, vStart);
        let back = nextKeyPos - 1;
        while (back > vStart && isWS(text[back])) back--;
        if (text[back] === ',') back--;
        while (back > vStart && isWS(text[back])) back--;
        vEnd = back;
      } else {
        const nextScenePos = text.indexOf('"' + fieldOrder[0] + '"', vStart);
        const boundary = nextScenePos !== -1 ? nextScenePos : text.length;
        let bracePos = boundary - 1;
        while (bracePos > vStart && text[bracePos] !== '}') bracePos--;
        let back = bracePos - 1;
        while (back > vStart && isWS(text[back])) back--;
        vEnd = back;
      }
      scene[fn] = text.substring(vStart, vEnd);
      pos = vEnd;
    }
    if (scene[fieldOrder[0]] !== undefined) scenes.push(scene);
    searchFrom = pos + 1;
  }
  return scenes;
}

// ── Parse scenes ──
let scenes = [];
let cleanResponse = '';
for (let i = 0; i < response.length; i++) {
  const c = response.charCodeAt(i);
  cleanResponse += (c < 32 && c !== 9 && c !== 10 && c !== 13) ? ' ' : response[i];
}
let jsonText = cleanResponse;
const codeBlockMatch = cleanResponse.match(/```(?:json)?\s*([\s\S]*?)```/);
if (codeBlockMatch) jsonText = codeBlockMatch[1].trim();
const jsonMatch = jsonText.match(/\{[\s\S]*\}/);
if (jsonMatch) jsonText = jsonMatch[0];

try {
  const sceneData = JSON.parse(jsonText);
  scenes = sceneData.scenes || [];
} catch (e) {
  scenes = extractScenes(jsonText);
  if (scenes.length === 0) throw new Error('Failed to parse scenes: ' + e.message);
}
if (scenes.length === 0) throw new Error('No scenes found');

function cleanText(text) {
  if (!text) return '';
  return text.replace(/"/g, "'").replace(/\n/g, " ").replace(/\r/g, " ").replace(/\t/g, " ").replace(/[\u0000-\u001F\u007F-\u009F]/g, "").trim();
}

// ── Generate FLUX images + Kling videos for each scene ──
const FAL_KEY = $env.FAL_KEY;
if (!FAL_KEY) throw new Error('FAL_KEY environment variable not set in n8n');

const videoUrls = [];

for (let i = 0; i < scenes.length; i++) {
  const scene = scenes[i];
  const imagePrompt = cleanText(scene.imagePrompt || '') + ', biblical, spiritual, reverent, cinematic lighting, professional photography, ultra-detailed, photorealistic, 8K quality';

  // Step 1: Generate FLUX image (synchronous)
  const fluxResp = await fetch('https://fal.run/fal-ai/flux-pro', {
    method: 'POST',
    headers: {
      'Authorization': 'Key ' + FAL_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      prompt: imagePrompt,
      image_size: 'landscape_16_9',
      num_inference_steps: 28,
      num_images: 1
    })
  });
  if (!fluxResp.ok) throw new Error('FLUX failed for scene ' + (i+1) + ': ' + await fluxResp.text());
  const fluxData = await fluxResp.json();
  const imageUrl = fluxData.images[0].url;

  // Step 2: Submit Kling job (async queue) — using Standard for speed (45s vs 90s)
  const motionPrompt = cleanText(scene.motionDescription || 'Slow cinematic camera movement with natural motion');
  const klingResp = await fetch('https://queue.fal.run/fal-ai/kling-video/v1.6/standard/image-to-video', {
    method: 'POST',
    headers: {
      'Authorization': 'Key ' + FAL_KEY,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      image_url: imageUrl,
      prompt: motionPrompt,
      duration: '5',
      cfg_scale: 0.5
    })
  });
  if (!klingResp.ok) throw new Error('Kling submit failed for scene ' + (i+1) + ': ' + await klingResp.text());
  const klingData = await klingResp.json();
  const statusUrl = klingData.status_url;
  const responseUrl = klingData.response_url;

  // Step 3: Poll until complete (max 3 min per scene, 15s intervals)
  let completed = false;
  for (let attempt = 0; attempt < 12; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 15000));
    const pollResp = await fetch(statusUrl, {
      headers: { 'Authorization': 'Key ' + FAL_KEY }
    });
    const pollData = await pollResp.json();
    if (pollData.status === 'COMPLETED') {
      completed = true;
      break;
    }
    if (pollData.status === 'FAILED' || pollData.status === 'ERROR') {
      throw new Error('Kling failed for scene ' + (i+1) + ': ' + JSON.stringify(pollData));
    }
  }
  if (!completed) throw new Error('Kling timed out for scene ' + (i+1));

  // Step 4: Fetch result
  const resultResp = await fetch(responseUrl, {
    headers: { 'Authorization': 'Key ' + FAL_KEY }
  });
  const resultData = await resultResp.json();
  const videoUrl = resultData.video?.url || resultData.data?.video?.url;
  if (!videoUrl) throw new Error('No video URL for scene ' + (i+1) + ': ' + JSON.stringify(resultData));

  videoUrls.push(videoUrl);
}

// ── Build template variables ──
const templateVariables = {};
scenes.forEach((scene, index) => {
  const sceneNum = index + 1;
  templateVariables['scene' + sceneNum + '_videoUrl'] = videoUrls[index];
  templateVariables['scene' + sceneNum + '_voiceOverText'] = cleanText(scene.voiceOverText || '');
  templateVariables['scene' + sceneNum + '_overlaidText'] = cleanText(scene.overlaidText || 'Scene ' + sceneNum);
});
templateVariables.totalScenes = scenes.length;

const result = {
  scenes: scenes,
  templateVariables: templateVariables,
  totalScenes: scenes.length,
  videoUrls: videoUrls,
  debugInfo: {
    parsedScenesCount: scenes.length,
    videoUrlsCount: videoUrls.length,
    timestamp: new Date().toISOString(),
    version: 'v8.0 - Kling AI Video Motion'
  }
};

return result;
"""

# Update the Enhanced Format node
enhanced_node = nodes_by_name["Enhanced Format for 16:9 Template"]
enhanced_node["name"] = "v8 FLUX + Kling + Template Vars"
enhanced_node["parameters"]["jsCode"] = new_jscode

# Update the JSON2Video node name
j2v_node = nodes_by_name["Generate 16:9 Spiritual Video"]
j2v_node["name"] = "Generate v8 Kling Video"

# Update connections: rename nodes in the connections map
old_to_new = {
    "Enhanced Format for 16:9 Template": "v8 FLUX + Kling + Template Vars",
    "Generate 16:9 Spiritual Video": "Generate v8 Kling Video",
}

# Rename connection keys
for old_name, new_name in old_to_new.items():
    if old_name in v8.get("connections", {}):
        v8["connections"][new_name] = v8["connections"].pop(old_name)

# Rename connection targets
for conn_name in v8["connections"]:
    for output_list in v8["connections"][conn_name].get("main", []):
        for link in output_list:
            node_ref = link.get("node", "")
            if node_ref in old_to_new:
                link["node"] = old_to_new[node_ref]

with open(BASE / "n8n/Biblical-Video-Workflow-v8.0.json", "w", encoding="utf-8") as f:
    json.dump(v8, f, indent=2, ensure_ascii=False)

print(f"v8 workflow created with {len(v8['nodes'])} nodes")
print("Code node updated with FLUX+Kling loop (Kling Standard for speed)")
