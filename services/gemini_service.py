import json
import re
import os
from google import genai
from google.genai import types
from services.env_loader import load_dotenv

class GeminiService:
    def __init__(self, project_id: str = None, location: str = None):
        # Ensure .env variables are loaded into environment
        load_dotenv()
        
        # Default to .env / environment or fallback
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or "veo-testing"
        self.location = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
        
        # Initialize Gemini client with Vertex AI enabled
        self.client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location=self.location
        )
        
        # Configurable models from .env
        self.extraction_model = os.environ.get("EXTRACTION_MODEL") or "gemini-3.1-pro-preview"
        self.embedding_model = os.environ.get("EMBEDDING_MODEL") or "gemini-embedding-2"

    def _format_json_response(self, response_text: str) -> dict | list:
        """Cleans up markdown code block markers and returns parsed JSON."""
        response_text_temp = re.sub(r"^```json\s*", "", response_text, flags=re.MULTILINE)
        response_text_temp = re.sub(r"^```\s*", "", response_text_temp, flags=re.MULTILINE)
        response_text_temp = re.sub(r"\s*```$", "", response_text_temp, flags=re.MULTILINE)
        return json.loads(response_text_temp.strip())

    def _run_extraction_pipeline(self, pdf_part: types.Part) -> list[dict]:
        """Runs the Gemini 3.1 Pro extraction pipeline on the provided document Part."""
        prompt_text = """Role and Objective:
You are a meticulous Data Extraction Assistant working for the Senior Editor of a leading Hindi daily newspaper. Your task is to read the provided PDF of our newspaper and extract every single news article into a distinct, structured format. You must treat the text with absolute journalistic integrity.
Strict Constraints (Zero Tolerance Policy):
NO Hallucination: You must extract the text exactly as it appears in the document. Do not summarize, rephrase, correct grammar, or add any outside information. If a word is cut off or illegible, insert [अस्पष्ट/Unreadable] instead of guessing.
NO Mixing of Articles: Newspaper layouts are complex. Do not bleed the text of one column into an adjacent, unrelated column. Pay strict attention to headlines, dividing lines, borders, and distinct font styles to identify where one article ends and another begins.
Extraction Guidelines:
Identify Boundaries: Every article typically has a Headline (बड़ा शीर्षक), sometimes a Sub-headline (उप-शीर्षक), a Dateline/Reporter Name (स्थान/संवाददाता), and Body Text (मुख्य समाचार). Use these elements as anchors to isolate individual stories.
Follow Column Flow (Read Vertically): Newspapers are read top-to-bottom in columns, NOT strictly left-to-right across the whole page. Ensure you are following the vertical flow of the text block for a specific headline before moving to the next column.
Ignore Non-News Elements: Exclude advertisements (विज्ञापन), page headers/footers, page numbers, and purely decorative text.
Handle Jumps/Continuations: If an article ends with "शेष पृष्ठ X पर" (Continued on page X), mark the end of that text clearly, but do not artificially merge it with unrelated articles on the current page.
Boxed Items: Treat text enclosed in boxes (इन्फोबॉक्स/साइड स्टोरी) as separate, standalone articles unless they explicitly share the exact same main headline.
Output Format:
Provide the output in the following JSON format to ensure clean, structured separation of every article. Use Hindi script (Devanagari) for the extracted text.
[
 {
  "article_id": 1,
  "page_number": "[Insert Page Number]",
  "headline": "[Extract Main Headline Here]",
  "sub_headline": "[Extract Sub-headline if present, otherwise null]",
  "dateline_or_author": "[Extract City, Date, or Reporter Name, e.g., 'नई दिल्ली (एजेंसी)' - otherwise null]",
  "body_text": "[Extract the exact full text of the article following the correct column reading order.]"
 },
 {
  "article_id": 2,
  "page_number": "[Insert Page Number]",
  "headline": "[Extract Main Headline Here]",
  "sub_headline": "[...]",
  "dateline_or_author": "[...]",
  "body_text": "[...]"
 }
]
Final Verification Step:
Before generating your final output, mentally review the body_text of each extracted article. If the text suddenly changes subject entirely (e.g., shifting from local politics to a sports match), you have likely mixed two articles. Fix the boundaries before outputting."""

        prompt_part = types.Part.from_text(text=prompt_text)
        contents = [
            types.Content(
                role="user",
                parts=[pdf_part, prompt_part]
            )
        ]
        
        config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            max_output_tokens=65535,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
            ],
            thinking_config=types.ThinkingConfig(thinking_level="HIGH")
        )
        
        response = self.client.models.generate_content(
            model=self.extraction_model,
            contents=contents,
            config=config
        )
        
        return self._format_json_response(response.text)

    def extract_articles(self, pdf_bytes: bytes) -> list[dict]:
        """
        Extracts articles from local Newspaper PDF bytes.
        """
        pdf_part = types.Part.from_bytes(
            data=pdf_bytes,
            mime_type="application/pdf",
        )
        return self._run_extraction_pipeline(pdf_part)

    def extract_articles_from_gcs(self, gcs_uri: str) -> list[dict]:
        """
        Extracts articles from GCS bucket path PDF (e.g. gs://bucket-name/file.pdf).
        """
        pdf_part = types.Part.from_uri(
            file_uri=gcs_uri,
            mime_type="application/pdf",
        )
        return self._run_extraction_pipeline(pdf_part)

    def generate_metadata(self, article_text: str) -> dict:
        """
        Generates SEO description, keywords, tags and summary for a given article.
        """
        prompt_text = """Role: Act as an expert SEO specialist and digital news editor.Task: I am going to provide you with the text of a news article. Please read the article carefully and generate the following metadata for it, ensuring it is optimized for search engines and maximizes click-through rates (CTR).CRITICAL INSTRUCTION: You must provide your response strictly in valid JSON format. Do not include any introductory text, explanations, or markdown formatting outside of the JSON object.Output Format: Please provide the output using the exact JSON structure below:
```json {
"meta_description": "Write a compelling summary of the Article Text that encourages readers to click. (Limit: 150-160 characters)",
"primary_keyword": "List 1 primary keyword here",
"secondary_keywords": [
"secondary keyword 1",
"secondary keyword 2",
"secondary keyword 3"
],
"tags": [
"Category 1",
"Category 2",
"Category 3"
],
"summmary": "A short summary of the Article Text"
}```
Article Text:"""
        
        prompt_part = types.Part.from_text(text=prompt_text)
        article_part = types.Part.from_text(text=article_text)
        
        contents = [
            types.Content(
                role="user",
                parts=[prompt_part, article_part]
            )
        ]
        
        config = types.GenerateContentConfig(
            temperature=1,
            top_p=0.95,
            max_output_tokens=65535,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
            ],
            thinking_config=types.ThinkingConfig(thinking_level="HIGH")
        )
        
        response = self.client.models.generate_content(
            model=self.extraction_model,
            contents=contents,
            config=config
        )
        
        return self._format_json_response(response.text)

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generates gemini-embedding-2 vector embedding for the text.
        """
        # Embeddings must use global location or specific supported location
        emb_client = genai.Client(
            vertexai=True,
            project=self.project_id,
            location="us" # gemini-embedding-2 runs in US region
        )
        content = types.Content(
            parts=[types.Part.from_text(text=text)]
        )
        result = emb_client.models.embed_content(
            model=self.embedding_model,
            contents=[content]
        )
        return result.embeddings[0].values

    def generate_newspaper_layout(self, articles: list[dict], persona: str) -> str:
        """
        Uses Gemini 3.1 Pro acting as a Chief Layout Editor to synthesize and format 
        selected news articles into a responsive standalone HTML newspaper front page
        matching the targeted reader persona.
        """
        articles_json = json.dumps(articles, ensure_ascii=False, indent=2)
        
        prompt_text = f"""Role and Objective:
You are the Executive Chief Editor and Master Typographer of a prestigious daily newspaper. Your task is to synthesize the provided set of news articles into a highly customized, standalone, responsive HTML front-page layout. You must employ elite print editorial standards—balancing typographic hierarchy, modular grid geometry, and advanced copyfitting—to tailor the page's visual language strictly to the specified Target Reader Persona.

Target Persona:
"{persona}"

Selected News Articles Data (JSON format):
{articles_json}

Editorial, Typographic & Styling Instructions:

1. Persona-Driven Art Direction & Typography:

Dynamic Visual Language: You must deeply analyze the Target Persona and adapt the typographic scale, column structure, and visual weight to their psychological and demographic profile.
Traditional/Conservative Persona: Emphasize formal symmetry, dense text layout, heavy Serif headline dominance (Martel), traditional column rules, and classic newspaper pacing.
Modern/Youth/Business Persona: Utilize an asymmetrical modular grid, Sans-Serif dominance for clean readability (Poppins), bolder contrast, larger photo placeholders, and scannable sidebars/infoboxes.
Typographic Hierarchy: Establish a rigorous visual hierarchy. The lead story must dominate (e.g., font-size: 2.5rem; font-weight: 900; line-height: 1.1;). Secondary stories and sidebars must scale down sequentially. Use kickers (sub-headlines above the main headline) and deckers (summaries below the headline) to build texture.
2. Content Veracity & Language Constraints:

CRITICAL CONSTRAINT (Strict Hindi Script): You MUST use the EXACT original Hindi body text (the verbatim article transcript) for the main text sections. Do NOT summarize, omit, correct grammar, or rephrase the core body transcripts.
Total Translation: ALL print-layout labels—folios, datelines, category tags (e.g., "FESTIVALS" → "त्यौहार"), issue dates, the masterhead, bylines (संवाददाता), column headers, and pull-quote attributions—MUST be written in Hindi script (Devanagari). No English words, badges, or placeholders may appear.
3. Advanced Copyfitting & Absolute Space Saturation (Zero Blank Space):

INCLUSION CONSTRAINT: You MUST place and layout EVERY single article provided in the input JSON. Do not drop or truncate any selected articles.
COMPOSING CONSTRAINT (The "Zero-Space" Rule): Real print broadsheets leave absolutely NO empty vertical spaces, orphan margins, or "dead air." The layout must seamlessly lock together like a puzzle to perfectly fill the sheet viewport.
Copyfitting Levers: To perfectly absorb and distribute space without breaking the layout, dynamically employ the following editorial tools:
Adjustable Leading & Kerning: Subtly tweak line-height and letter-spacing within standard acceptable print ranges based on article length.
Modular Drop Caps: Use <span class="drop-cap"> (float: left; font-size: 3.5rem; line-height: 0.8; padding-right: 0.5rem;) to begin major articles and absorb line space.
Variable Pull Quotes: Intercalate striking quote highlights (<blockquote>) within long columns. Expand or contract their padding, font size, and border weights to act as vertical shock absorbers.
Flexible Image Placeholders: Scale .photo-placeholder heights (e.g., varying from 150px to 300px) strategically to push text down and perfectly align the bottoms of adjacent columns (avoiding tombstoning).
Sidebar Infoboxes: Package minor stories into shaded boxes (<aside>). Use them to fill awkward narrow columns.
4. Photojournalism & Visual Placeholders:

Incorporate elegant, highly visual image placeholders at the head of major articles or anchored inside columns.
Use <div class="photo-placeholder">. Style it with a subtle grey background, an SVG icon of a camera/photo frame, a thin border, and a meticulously placed, italicized Hindi caption (lang="hi") that contextualizes the story (e.g., 'भोपाल में विवाह स्थल की सजावट का एक दृश्य').
5. Structural Multi-Column Layout (High-Fidelity Broadsheet HTML/CSS):

Wrap the entire page inside a <div class="newspaper-sheet">.
Divide the layout using CSS multi-column layouts (column-count, column-gap, column-rule). Let the Hindi Devanagari text split and flow naturally (break-inside: auto; on main paragraphs). Ensure columns are fully justified (text-align: justify; hyphens: auto;) for an authentic print block feel.
High-Fidelity Scale (EXACT 749mm × 597mm):
Enforce the following styles globally to replicate a broadsheet standard size (1.255 aspect ratio):"""

        prompt_text = prompt_text+"""html, body {
  min-height: 100% !important;
  height: auto !important; /* allow vertical growth */
  margin: 0 !important;
  padding: 0 !important;
  background-color: #ffffff !important;
  display: flex !important;
  flex-direction: column !important;
  box-sizing: border-box !important;
  -webkit-font-smoothing: antialiased;
}
.newspaper-sheet {
  background-color: #ffffff !important;
  box-sizing: border-box !important;
  width: 100% !important;
  min-height: 100vh !important; /* fill the viewport by default */
  height: auto !important; /* stretch naturally if content overflows */
  padding: 5% 6% !important;
  display: flex !important;
  flex-direction: column !important;
  position: relative !important;
  flex: 1 !important;
}
.masterhead-container { flex-shrink: 0 !important; }
.newspaper-columns { flex: 1 !important; margin-top: 20px !important; }

@media print {
  @page { size: 597mm 749mm; margin: 0; }
  html, body {
    background-color: #ffffff !important; padding: 0 !important; margin: 0 !important;
    width: 100% !important; height: 100% !important; overflow: hidden !important;
  }
  .newspaper-sheet {
    margin: 0 !important; border: none !important; box-shadow: none !important;
    width: 597mm !important; height: 749mm !important;
    padding: 20mm 25mm !important; aspect-ratio: none !important;
  }
}
6. Iframe Sandboxing & Font Isolation:

This HTML will render inside an isolated iframe. You MUST explicitly load Google Fonts in the <head>:
<link href="https://fonts.googleapis.com/css2?family=Martel:wght@400;700;900&family=Poppins:wght@400;600;700&display=swap" rel="stylesheet">
Prevent Devanagari blocks from rendering as empty squares by enforcing global fallbacks:
body, h1, h2, h3, h4, h5, h6, p, div, span, strong, em, label {
  font-family: 'Poppins', 'Martel', 'Noto Sans Devanagari', 'Lohit Devanagari', sans-serif !important;
}
h1, h2, h3, h4, h5 { font-family: 'Martel', serif !important; font-weight: 700; }

/* Custom sleek scrollbar for natural copypaper reading */
::-webkit-scrollbar {
  width: 6px !important;
  height: 6px !important;
}
::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.02) !important;
}
::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.12) !important;
  border-radius: 3px !important;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.24) !important;
}
7. Strict Output Format Constraint:

Output ONLY valid HTML code starting with <!DOCTYPE html> and ending with </html>.
Do NOT wrap the output in markdown code block backticks (i.e., NO html or at start and end).
Do NOT include any introductory or concluding conversational text. Provide ONLY the dropship-ready raw HTML page payload.
"""

        prompt_part = types.Part.from_text(text=prompt_text)
        contents = [
            types.Content(
                role="user",
                parts=[prompt_part]
            )
        ]
        
        config = types.GenerateContentConfig(
            temperature=0.8,
            top_p=0.95,
            max_output_tokens=65535,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
            ],
            thinking_config=types.ThinkingConfig(thinking_level="HIGH")
        )
        
        response = self.client.models.generate_content(
            model=self.extraction_model,
            contents=contents,
            config=config
        )
        
        # Clean up markdown backticks if the model accidentally printed them anyway
        clean_html = response.text.strip()
        if clean_html.startswith("```html"):
            clean_html = clean_html[7:]
        elif clean_html.startswith("```"):
            clean_html = clean_html[3:]
        if clean_html.endswith("```"):
            clean_html = clean_html[:-3]
            
        return clean_html.strip()
