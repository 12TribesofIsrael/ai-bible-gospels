"""Update the Perplexity prompt in v7.2 and v8.0 workflows with ethnicity-aware character depiction rules."""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent

NEW_PROMPT_CONTENT = (
    'You are a Biblical storytelling and video production expert specializing in authentic Black Hebrew Israelite biblical content. '
    'Create a script for a PRODUCTION-QUALITY 20-scene video that narrates the Bible chapter content provided: "${inputText}" exactly as it is—word for word and line for line. '
    'Do not summarize or paraphrase any part of the biblical text. Instead, break the Bible chapter into EXACTLY 20 SCENES that facilitate the creation of engaging biblical video content for a full-length production video.\n\n'

    'CRITICAL CHARACTER ETHNICITY RULES - READ CAREFULLY:\n'
    'Every character MUST be depicted according to their biblical nationality:\n\n'

    'ISRAELITES / HEBREWS (default for all Israelite characters):\n'
    '- Black Hebrew Israelites with rich, deeply melanated dark skin\n'
    '- Natural Afro-textured hair: locs, braids, twists, afros, or traditional head wraps\n'
    '- Traditional Hebrew garments: robes, tunics, prayer shawls with visible tzitzit (fringes), sandals\n'
    '- Use terms: "deeply melanated," "rich dark skin," "African Hebrew heritage," "Afro-textured hair"\n\n'

    'ROMANS:\n'
    '- Caucasian/European with light olive or fair skin\n'
    '- Roman military armor, togas, laurel wreaths, red cloaks, gladius swords\n'
    '- Clean-shaven or short-cropped hair, Roman military styling\n\n'

    'GREEKS / MACEDONIANS:\n'
    '- Mediterranean/European with olive to fair skin\n'
    '- Greek tunics, Hellenistic armor, plumed helmets, draped robes\n'
    '- Curly or wavy hair, Greek styling\n\n'

    'EGYPTIANS:\n'
    '- North African with brown/dark brown skin\n'
    '- Egyptian headdresses, linen garments, gold jewelry, kohl-lined eyes\n\n'

    'PERSIANS / MEDES:\n'
    '- Middle Eastern with olive to brown skin\n'
    '- Persian robes, ornate headpieces, flowing garments, decorative armor\n\n'

    'BABYLONIANS / ASSYRIANS:\n'
    '- Middle Eastern with olive to brown skin\n'
    '- Ornate robes, long curled beards, Mesopotamian crowns and jewelry\n\n'

    'PHILISTINES / CANAANITES:\n'
    '- Mediterranean/Levantine appearance\n'
    '- Bronze armor, distinctive feathered headdresses (Philistines), Canaanite garments\n\n'

    'DEFAULT RULE: If the text mentions a nation not listed above, depict them with their historically accurate ethnicity. '
    'ONLY Israelites/Hebrews are depicted as Black Hebrew Israelites.\n\n'

    'For each non-empty verse or sentence of the biblical text, create a separate scene where both the overlaid text and the voice-over text match the biblical text exactly.\n\n'

    'If a verse is too short to meet the minimum voice-over text length of 20 words, combine it with the following verse(s) without altering the original biblical wording.\n\n'

    'Your output must be in JSON format following this exact schema:\n\n'
    '{\n'
    '  "scenes": [\n'
    '    {\n'
    '      "overlaidText": "Direct biblical phrase from the text (3-8 words)",\n'
    '      "voiceOverText": "Exact biblical text word-for-word (20+ words minimum)",\n'
    '      "imagePrompt": "Identify each character\'s nation and depict with correct ethnicity per rules above - [detailed biblical scene description] - photorealistic, ancient setting, reverent biblical atmosphere",\n'
    '      "motionDescription": "Natural motion for this moment — e.g. \'Camera slowly pulls back as figure raises hands toward golden sky\' or \'Robes ripple in wind, crowd parts like a wave\'"\n'
    '    }\n'
    '  ]\n'
    '}\n\n'

    'ETHNICITY-AWARE IMAGE PROMPT REQUIREMENTS:\n'
    '- FIRST identify which nation/people each character in the scene belongs to\n'
    '- ISRAELITES: Start with "Black Hebrew Israelite with deeply melanated skin, Afro-textured hair (locs/braids), wearing traditional Hebrew robes with visible tzitzit fringes"\n'
    '- ROMANS: Describe as "Caucasian Roman soldier/official with light skin, Roman armor/toga"\n'
    '- GREEKS/MACEDONIANS: Describe as "Mediterranean Greek warrior/figure with olive skin, Hellenistic armor/robes"\n'
    '- EGYPTIANS: Describe as "Egyptian figure with brown skin, traditional Egyptian garments and headdress"\n'
    '- PERSIANS/MEDES: Describe as "Persian figure with olive-brown skin, ornate Persian robes"\n'
    '- For scenes with MULTIPLE nations (e.g. Israelites before a Roman governor), depict EACH character according to their own nation\'s ethnicity\n'
    '- ADD specific scene details after character descriptions\n'
    '- INCLUDE: "photorealistic, ancient biblical times, reverent spiritual atmosphere"\n'
    '- CAMERA ANGLE VARIETY: Alternate close-up / medium shot / wide shot / aerial — never same angle twice in a row\n'
    '- LIGHTING CONTRAST: Specify a dramatic light source per scene — "shaft of divine light from above", "torch-lit darkness with one focal point", "golden hour rays behind silhouette"\n\n'

    'IMPORTANT GUIDELINES:\n'
    '- Use the biblical text exactly as provided—word for word and line for line\n'
    '- Create a separate scene for each verse or sentence in the biblical text\n'
    '- VoiceOverText must be the exact biblical wording, no paraphrasing\n'
    '- OverlaidText should be direct quotes from the biblical text (3-8 words)\n'
    '- You MUST create EXACTLY 20 scenes regardless of input text length - distribute the content intelligently across all 20 scenes\n'
    '- For shorter texts, expand descriptions and context while maintaining biblical accuracy\n'
    '- For longer texts, segment logically while preserving all content across the 20 scenes\n'
    '- Focus on maintaining exact biblical wording and ethnicity-accurate visual representation\n'
    '- CRITICAL: Israelites = Black Hebrew Israelites. All other nations = their own historical ethnicity. Never make Romans, Greeks, Egyptians, or Persians look like Black Israelites.\n\n'

    'EXAMPLE IMAGE PROMPTS:\n'
    '- Israelite scene: "Black Hebrew Israelite man with deeply melanated skin and natural locs, wearing traditional Hebrew robes with visible tzitzit fringes, standing in ancient temple, photorealistic, reverent biblical atmosphere"\n'
    '- Roman scene: "Caucasian Roman centurion with light skin in polished bronze armor and red cloak, standing before deeply melanated Black Hebrew Israelite prisoners in Hebrew garments, ancient Jerusalem courtyard, photorealistic"\n'
    '- Greek scene: "Mediterranean Greek king Alexander with olive skin in Hellenistic armor and plumed helmet, conquering ancient city, photorealistic, dramatic cinematic lighting"\n'
    '- Mixed scene: "Deeply melanated Black Hebrew Israelite elders with locs and tzitzit-fringed robes standing before olive-skinned Persian king Darius in ornate Persian crown and robes, ancient throne room, photorealistic"\n\n'

    'CRITICAL: Return ONLY raw JSON. No markdown, no code fences, no triple-backtick blocks, no commentary before or after the JSON. Your response must start with { and end with }.'
)

# Build the full jsCode
new_jscode = (
    '// Get the input text from previous node\n'
    "const inputText = $('Bible Chapter Text Input').item.json.inputText;\n\n"
    '// ETHNICITY-AWARE Build the request payload with nation-accurate character depiction\n'
    'const requestPayload = {\n'
    '  model: "sonar-pro",\n'
    '  messages: [{\n'
    '    role: "user", \n'
    '    content: `' + NEW_PROMPT_CONTENT + '`\n'
    '  }],\n'
    '  max_tokens: 5000,\n'
    '  temperature: 0.7,\n'
    '  response_format: {\n'
    '    type: "json_schema",\n'
    '    json_schema: {\n'
    '      name: "biblical_scenes",\n'
    '      schema: {\n'
    '        type: "object",\n'
    '        properties: {\n'
    '          scenes: {\n'
    '            type: "array",\n'
    '            items: {\n'
    '              type: "object",\n'
    '              properties: {\n'
    '                overlaidText:      { type: "string" },\n'
    '                voiceOverText:     { type: "string" },\n'
    '                imagePrompt:       { type: "string" },\n'
    '                motionDescription: { type: "string" }\n'
    '              },\n'
    '              required: ["overlaidText", "voiceOverText", "imagePrompt", "motionDescription"],\n'
    '              additionalProperties: false\n'
    '            }\n'
    '          }\n'
    '        },\n'
    '        required: ["scenes"],\n'
    '        additionalProperties: false\n'
    '      }\n'
    '    }\n'
    '  }\n'
    '};\n\n'
    '// Return the payload\n'
    'return [{\n'
    '  json: requestPayload\n'
    '}];'
)

# Update both workflow files
for fname in [
    'n8n/Biblical-Video-Workflow-v7.2.json',
    'n8n/Biblical-Video-Workflow-v8.0.json',
]:
    fpath = BASE / fname
    if not fpath.exists():
        print(f"SKIP (not found): {fname}")
        continue

    with open(fpath, 'r', encoding='utf-8') as f:
        wf = json.load(f)

    updated = False
    for n in wf['nodes']:
        if n['name'] == 'Biblical Content Prompt Builder':
            n['parameters']['jsCode'] = new_jscode
            updated = True

    if updated:
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(wf, f, indent=2, ensure_ascii=False)
        print(f"Updated: {fname}")
    else:
        print(f"Node not found in: {fname}")

print("Done!")
