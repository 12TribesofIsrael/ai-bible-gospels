"""Rebuild v8.0 workflow to use HTTP Request nodes instead of fetch() in Code node.
n8n Cloud blocks fetch/require in Code nodes, so we use native HTTP Request nodes."""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent
FAL_KEY = "f5a5a176-33b5-4c3d-8ffc-a7cf426e5926:f784581a020d123a488fc2094d472d0f"

with open(BASE / "n8n/Biblical-Video-Workflow-v8.0.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

# Keep all existing nodes EXCEPT the old combined Code node
old_code_name = "v8 FLUX + Kling + Template Vars"
wf["nodes"] = [n for n in wf["nodes"] if n["name"] != old_code_name]

# ── Parse Scenes Code Node ──
parse_scenes_code = (
    "// v8.0 Parse Perplexity response into individual scene items\n"
    "const response = items[0].json.choices[0].message.content;\n"
    "\n"
    "// Field-name-anchored extraction (same as v7.2)\n"
    "function extractScenes(text) {\n"
    "  const fieldOrder = ['overlaidText', 'voiceOverText', 'imagePrompt', 'motionDescription'];\n"
    "  const scenes = [];\n"
    "  let searchFrom = 0;\n"
    "  function isWS(ch) { return ch === ' ' || ch === '\\n' || ch === '\\r' || ch === '\\t'; }\n"
    "  while (true) {\n"
    '    const firstKey = \'"\' + fieldOrder[0] + \'"\';\n'
    "    const sceneStart = text.indexOf(firstKey, searchFrom);\n"
    "    if (sceneStart === -1) break;\n"
    "    const scene = {};\n"
    "    let pos = sceneStart;\n"
    "    for (let fi = 0; fi < fieldOrder.length; fi++) {\n"
    "      const fn = fieldOrder[fi];\n"
    "      const nextFn = fi < fieldOrder.length - 1 ? fieldOrder[fi + 1] : null;\n"
    '      const keyPat = \'"\' + fn + \'"\';\n'
    "      const keyPos = text.indexOf(keyPat, pos);\n"
    "      if (keyPos === -1) break;\n"
    "      const colonPos = text.indexOf(':', keyPos + keyPat.length);\n"
    '      const openQuotePos = text.indexOf(\'"\', colonPos + 1);\n'
    "      const vStart = openQuotePos + 1;\n"
    "      let vEnd;\n"
    "      if (nextFn) {\n"
    '        const nextKeyPat = \'"\' + nextFn + \'"\';\n'
    "        const nextKeyPos = text.indexOf(nextKeyPat, vStart);\n"
    "        let back = nextKeyPos - 1;\n"
    "        while (back > vStart && isWS(text[back])) back--;\n"
    "        if (text[back] === ',') back--;\n"
    "        while (back > vStart && isWS(text[back])) back--;\n"
    "        vEnd = back;\n"
    "      } else {\n"
    '        const nextScenePos = text.indexOf(\'"\' + fieldOrder[0] + \'"\'  , vStart);\n'
    "        const boundary = nextScenePos !== -1 ? nextScenePos : text.length;\n"
    "        let bracePos = boundary - 1;\n"
    "        while (bracePos > vStart && text[bracePos] !== '}') bracePos--;\n"
    "        let back = bracePos - 1;\n"
    "        while (back > vStart && isWS(text[back])) back--;\n"
    "        vEnd = back;\n"
    "      }\n"
    "      scene[fn] = text.substring(vStart, vEnd);\n"
    "      pos = vEnd;\n"
    "    }\n"
    "    if (scene[fieldOrder[0]] !== undefined) scenes.push(scene);\n"
    "    searchFrom = pos + 1;\n"
    "  }\n"
    "  return scenes;\n"
    "}\n"
    "\n"
    "let scenes = [];\n"
    "let cleanResponse = '';\n"
    "for (let i = 0; i < response.length; i++) {\n"
    "  const c = response.charCodeAt(i);\n"
    "  cleanResponse += (c < 32 && c !== 9 && c !== 10 && c !== 13) ? ' ' : response[i];\n"
    "}\n"
    "let jsonText = cleanResponse;\n"
    "const codeBlockMatch = cleanResponse.match(/```(?:json)?\\s*([\\s\\S]*?)```/);\n"
    "if (codeBlockMatch) jsonText = codeBlockMatch[1].trim();\n"
    "const jsonMatch = jsonText.match(/\\{[\\s\\S]*\\}/);\n"
    "if (jsonMatch) jsonText = jsonMatch[0];\n"
    "\n"
    "try {\n"
    "  const sceneData = JSON.parse(jsonText);\n"
    "  scenes = sceneData.scenes || [];\n"
    "} catch (e) {\n"
    "  scenes = extractScenes(jsonText);\n"
    "  if (scenes.length === 0) throw new Error('Failed to parse scenes: ' + e.message);\n"
    "}\n"
    "if (scenes.length === 0) throw new Error('No scenes found');\n"
    "\n"
    "function cleanText(text) {\n"
    "  if (!text) return '';\n"
    '  return text.replace(/"/g, "\'").replace(/\\n/g, " ").replace(/\\r/g, " ").replace(/\\t/g, " ").replace(/[\\u0000-\\u001F\\u007F-\\u009F]/g, "").trim();\n'
    "}\n"
    "\n"
    "// Output one item per scene for HTTP Request nodes to process\n"
    "return scenes.map((scene, index) => ({\n"
    "  json: {\n"
    "    sceneNum: index + 1,\n"
    "    imagePrompt: cleanText(scene.imagePrompt || '') + ', biblical, spiritual, reverent, cinematic lighting, professional photography, ultra-detailed, photorealistic, 8K quality',\n"
    "    voiceOverText: cleanText(scene.voiceOverText || ''),\n"
    "    overlaidText: cleanText(scene.overlaidText || 'Scene ' + (index + 1)),\n"
    "    motionDescription: cleanText(scene.motionDescription || 'Slow cinematic camera movement with natural motion')\n"
    "  }\n"
    "}));\n"
)

parse_scenes_node = {
    "parameters": {"jsCode": parse_scenes_code},
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [-976, 240],
    "id": "a1b2c3d4-0001-4000-8000-000000000001",
    "name": "Parse Scenes"
}

# ── FLUX Image HTTP Request Node ──
flux_node = {
    "parameters": {
        "method": "POST",
        "url": "https://fal.run/fal-ai/flux-pro",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Authorization", "value": "Key " + FAL_KEY},
                {"name": "Content-Type", "value": "application/json"}
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ prompt: $json.imagePrompt, image_size: 'landscape_16_9', num_inference_steps: 28, num_images: 1 }) }}",
        "options": {
            "timeout": 120000
        }
    },
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [-776, 240],
    "id": "a1b2c3d4-0002-4000-8000-000000000002",
    "name": "Generate FLUX Image"
}

# ── Kling Video HTTP Request Node (sync via fal.run) ──
kling_node = {
    "parameters": {
        "method": "POST",
        "url": "https://fal.run/fal-ai/kling-video/v1.6/standard/image-to-video",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Authorization", "value": "Key " + FAL_KEY},
                {"name": "Content-Type", "value": "application/json"}
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ image_url: $json.images[0].url, prompt: $('Parse Scenes').item.json.motionDescription, duration: '5', cfg_scale: 0.5 }) }}",
        "options": {
            "timeout": 300000
        }
    },
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [-576, 240],
    "id": "a1b2c3d4-0003-4000-8000-000000000003",
    "name": "Generate Kling Video"
}

# ── Build Template Vars Code Node ──
build_vars_code = (
    "// Aggregate all scene results into template variables for JSON2Video\n"
    "const allScenes = $('Parse Scenes').all();\n"
    "const templateVariables = {};\n"
    "\n"
    "for (let i = 0; i < items.length; i++) {\n"
    "  const sceneNum = allScenes[i].json.sceneNum;\n"
    "  const videoUrl = items[i].json.video?.url || items[i].json.data?.video?.url || '';\n"
    "  templateVariables['scene' + sceneNum + '_videoUrl'] = videoUrl;\n"
    "  templateVariables['scene' + sceneNum + '_voiceOverText'] = allScenes[i].json.voiceOverText;\n"
    "  templateVariables['scene' + sceneNum + '_overlaidText'] = allScenes[i].json.overlaidText;\n"
    "}\n"
    "templateVariables.totalScenes = items.length;\n"
    "\n"
    "return [{\n"
    "  json: {\n"
    "    templateVariables: templateVariables,\n"
    "    totalScenes: items.length,\n"
    "    debugInfo: {\n"
    "      timestamp: new Date().toISOString(),\n"
    "      version: 'v8.0 - Kling AI Video Motion'\n"
    "    }\n"
    "  }\n"
    "}];\n"
)

build_vars_node = {
    "parameters": {"jsCode": build_vars_code},
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [-376, 240],
    "id": "a1b2c3d4-0004-4000-8000-000000000004",
    "name": "Build Template Vars"
}

# Add new nodes
wf["nodes"].extend([parse_scenes_node, flux_node, kling_node, build_vars_node])

# Fix JSON2Video node to reference Build Template Vars
for node in wf["nodes"]:
    if node["name"] == "Generate v8 Kling Video":
        node["parameters"]["jsonBody"] = node["parameters"]["jsonBody"].replace(
            "$('Enhanced Format for 16:9 Template')",
            "$('Build Template Vars')"
        )
        node["position"] = [-176, 240]
    # Fix Check Video Status to reference correct node
    if node["name"] == "Check Video Status":
        if "queryParameters" in node["parameters"]:
            for p in node["parameters"]["queryParameters"]["parameters"]:
                if "Generate 16:9 Spiritual Video" in p.get("value", ""):
                    p["value"] = p["value"].replace(
                        "Generate 16:9 Spiritual Video",
                        "Generate v8 Kling Video"
                    )

# Update connections
if old_code_name in wf["connections"]:
    del wf["connections"][old_code_name]

wf["connections"]["Perplexity AI Scene Generator"] = {
    "main": [[{"node": "Parse Scenes", "type": "main", "index": 0}]]
}
wf["connections"]["Parse Scenes"] = {
    "main": [[{"node": "Generate FLUX Image", "type": "main", "index": 0}]]
}
wf["connections"]["Generate FLUX Image"] = {
    "main": [[{"node": "Generate Kling Video", "type": "main", "index": 0}]]
}
wf["connections"]["Generate Kling Video"] = {
    "main": [[{"node": "Build Template Vars", "type": "main", "index": 0}]]
}
wf["connections"]["Build Template Vars"] = {
    "main": [[{"node": "Generate v8 Kling Video", "type": "main", "index": 0}]]
}

with open(BASE / "n8n/Biblical-Video-Workflow-v8.0.json", "w", encoding="utf-8") as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print(f"Rebuilt v8 workflow with {len(wf['nodes'])} nodes")
print("Flow: Perplexity -> Parse Scenes (Code) -> FLUX Image (HTTP) -> Kling Video (HTTP) -> Build Template Vars (Code) -> JSON2Video (HTTP)")
