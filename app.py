import pdfplumber           # reader only, not a pdf writer
from fpdf import FPDF
import unicodedata
import os,sys
from openai import OpenAI
if sys.platform.startswith("win"):
    import asyncio
    # Force a loop that supports subprocesses on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import streamlit as st
import re
import html
from pathlib import Path
from playwright.sync_api import sync_playwright
import base64
from pathlib import Path
import datetime, html as _html

def encode_image_to_data_uri(path: str) -> str:
    ext = Path(path).suffix.lower().lstrip(".")
    mime = "image/png" if ext == "png" else "image/jpeg"
    data = Path(path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"

# usage
logo_url = encode_image_to_data_uri("C:/code/Projects/Medical Summary/assets/logo.png")

# remove emoji variation selector (often breaks width calc)
VS16 = "\uFE0F"
# crude range for supplementary-plane chars (most emojis live here)
SUPPLEMENTARY = re.compile(r'[\U00010000-\U0010FFFF]')

# optional: remove supplementary-plane chars (most emojis)
def pdf_to_text(pdf_path, txt_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"✅ Extracted text saved to {txt_path}")
    return txt_path

def read_file_to_string(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()
    return content

def read_doctor_and_lab(file_path: str):
    doctor, lab = None, None

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.lower().startswith("doctor"):
                # split at ':' and take the right-hand side
                doctor = line.split(":", 1)[1].strip()
            elif line.lower().startswith("lab"):
                lab = line.split(":", 1)[1].strip()

    return doctor, lab

def get_openai_response(prompt: str, model: str = "gpt-4.1-mini") -> str:
    # Initialize client (API key must be set as env var OPENAI_API_KEY)
    client = OpenAI()

    # Send request
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}]
    )

    # Extract response text
    output = response.choices[0].message.content
    #print("AI Response:", output)
    return output

def _wrap_lines(pdf: FPDF, text: str, max_w: float):
    """Yield lines wrapped to fit max_w using current font."""
    lines = []
    for raw_line in text.splitlines() or [""]:
        # split by spaces but preserve very long tokens by splitting further
        parts = raw_line.split(" ")
        line = ""
        for part in parts:
            token = part or ""
            if line:
                test = line + " " + token
            else:
                test = token

            if pdf.get_string_width(test) <= max_w:
                line = test
                continue

            # current line full; store it
            if line:
                lines.append(line)
                line = ""

            # token may still be too wide; split by characters
            buf = ""
            for ch in token:
                if pdf.get_string_width(buf + ch) <= max_w:
                    buf += ch
                else:
                    if buf:
                        lines.append(buf)
                    buf = ch
            if buf:
                line = buf

        lines.append(line)
    return lines

import re, html
from playwright.sync_api import sync_playwright

HASH_TOKEN_OPEN = "«HASH_OPEN»"
HASH_TOKEN_CLOSE = "«HASH_CLOSE»"
STAR_TOKEN_OPEN = "«STAR_OPEN»"
STAR_TOKEN_CLOSE = "«STAR_CLOSE»"

def markup_hash_spans(raw: str) -> str:
    """
    Replace all ##...## and ***...*** with tokens,
    escape everything else, then replace tokens with styled spans.
    """

    # Step 1: replace ##...## with tokens
    def _repl_hash(m: re.Match) -> str:
        inner = m.group(1).strip()
        return f"{HASH_TOKEN_OPEN}{html.escape(inner)}{HASH_TOKEN_CLOSE}"

    marked = re.sub(r"##(.*?)##", _repl_hash, raw, flags=re.DOTALL)

    # Step 2: replace ***...*** with tokens
    def _repl_star(m: re.Match) -> str:
        inner = m.group(1).strip()
        return f"{STAR_TOKEN_OPEN}{html.escape(inner)}{STAR_TOKEN_CLOSE}"

    marked = re.sub(r"\*\*\*(.*?)\*\*\*", _repl_star, marked, flags=re.DOTALL)

    # Step 3: escape everything else
    escaped = html.escape(marked).replace("\t", "    ")

    # Step 4: restore tokens into spans
    escaped = escaped.replace(html.escape(HASH_TOKEN_OPEN), '<span class="hash-chunk">')
    escaped = escaped.replace(html.escape(HASH_TOKEN_CLOSE), '</span>')

    escaped = escaped.replace(html.escape(STAR_TOKEN_OPEN), '<span class="star-chunk">')
    escaped = escaped.replace(html.escape(STAR_TOKEN_CLOSE), '</span>')

    return escaped


HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  :root {{
    --bg:#ffffff; --fg:#1f2328; --muted:#57606a; --card:#f6f8fa; --accent:#0b5fff;
  }}
  @page {{ size: A4; margin: 28mm 18mm 22mm 18mm; }}
  body {{
    margin:0; background:var(--bg); color:var(--fg);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",
                 "Inter",Arial,"Noto Sans",
                 "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji","Twemoji Mozilla","EmojiOne Color",
                 "Noto Sans Symbols","Noto Emoji","DejaVu Sans",sans-serif;
    font-size:11pt; line-height:1.45;
  }}
  header {{
    display:flex; align-items:center; justify-content:space-between;
    border-bottom:1px solid #e5e7eb; padding:8px 0 10px; margin:0 0 10px;
  }}
  .brand {{
    display:flex; gap:10px; align-items:center;
  }}
  .brand h1 {{ font-size:16pt; margin:0; font-weight:600; }}
  .meta-block {{ font-size:9.5pt; color:var(--muted); text-align:right; line-height:1.2; }}
  .meta-block div strong {{ color:#111; }}
  .logo {{
    width:28px; height:28px; border-radius:6px; object-fit:cover; display:{logo_display};
  }}
  main {{}}
  .bubble {{
    margin-top:8px; background:var(--card); border-radius:12px; padding:14px 16px;
    white-space:pre-wrap; word-wrap:break-word; overflow-wrap:anywhere;
  }}
  .hash-chunk {{
    font-weight:700; font-size:120%;
    font-family:"Noto Serif","Georgia","Times New Roman",Times,serif,
                "Noto Color Emoji","Apple Color Emoji","Segoe UI Emoji","Twemoji Mozilla","EmojiOne Color";
  }}
  .star-chunk {{
    font-weight:700;
    font-size:110%; /* 10% bigger */
  }}
</style>
</head>
<body>
<header>
  <div class="brand">
    <img class="logo" src="{logo_url}" alt="logo">
    <h1>{title}</h1>
  </div>
  <div class="meta-block">
    {doctor_line}
    {lab_line}
    <div><strong>Date:</strong> {date}</div>
  </div>
</header>
<main>
  <div class="bubble">{content}</div>
</main>
</body>
</html>"""

def text_to_pdf_rich_chrome(
    text: str,
    pdf_path: str,
    title: str = "Medical Report Made Easy",
    subtitle: str = "",
    doctor: str | None = None,
    lab: str | None = None,
    logo_url: str | None = None,
):
    import datetime, html as _html
    from pathlib import Path

    # Process the text for ##...## and ***...***
    safe = markup_hash_spans(text)

    doctor_line = f'<div><strong>Doctor:</strong> {_html.escape(doctor)}</div>' if doctor else ""
    lab_line    = f'<div><strong>Lab:</strong> {_html.escape(lab)}</div>' if lab else ""
    date_str    = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    tmpl = HTML_TEMPLATE.format(
        title=_html.escape(title),
        subtitle=_html.escape(subtitle),
        content=safe,
        doctor_line=doctor_line,
        lab_line=lab_line,
        date=date_str,
        logo_url=_html.escape(logo_url) if logo_url else "",
        logo_display="block" if logo_url else "none",
    )

    pdf_path = str(Path(pdf_path).resolve())
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(tmpl)
        page.pdf(
            path=pdf_path,
            format="A4",
            margin={"top":"28mm","right":"18mm","bottom":"22mm","left":"18mm"},
            print_background=True,
        )
        browser.close()



# Example usage:
prompt = read_file_to_string("humans.txt")
#prompt = read_file_to_string("pets.txt")

#print(prompt)
#get_openai_response(prompt + '\n' + report_data)
#sys.exit(1)

st.title("📄 Health Summary Assistant")

import re

def cleanAIResp(text: str):
    # Extract name if exists
    m_name = re.search(r'^\s*name\s*:\s*(.+?)\s*$', text, flags=re.IGNORECASE | re.MULTILINE)
    name_value = m_name.group(1) if m_name else None

    # Extract owner if exists
    m_owner = re.search(r'^\s*owner\s*:\s*(.+?)\s*$', text, flags=re.IGNORECASE | re.MULTILINE)
    owner_value = m_owner.group(1) if m_owner else None

    # Find "Hi" and cut everything before it
    m_hi = re.search(r'\bHi\b.*', text, flags=re.IGNORECASE | re.DOTALL)
    if m_hi:
        cleaned_text = m_hi.group(0)
    else:
        # fallback: just remove name/owner lines if "Hi" not found
        cleaned_text = re.sub(r'^\s*(name|owner)\s*:\s*.+\n?', '', text, flags=re.IGNORECASE | re.MULTILINE)
    print(name_value, ' : ', owner_value)
    cleaned_text = cleaned_text.strip().rstrip(" ,.`")
    print(cleaned_text.strip())
    return cleaned_text.strip()

def ensure_dirs(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=True)

doctor, lab = read_doctor_and_lab("data/clinic_details.txt")
logo_url = "http://localhost:8501/assets/logo.png"
uploaded_file = st.file_uploader("Upload a PDF for the report", type="pdf")
if uploaded_file:
    ensure_dirs("reports/uploads", "reports/summaries")
    with st.status("Starting…", expanded=True) as status:
        st.success("✅ File uploaded successfully.")
        # get filename without extension
        base_name, _ = os.path.splitext(uploaded_file.name)
        output_path = f"reports/uploads/{base_name}.txt"
        status.update(label="Extracting Bio Markers from PDF…")
        output_path = pdf_to_text(uploaded_file, output_path)
        report_data = read_file_to_string(output_path)
        status.update(label="Smart processing of your report is in progress……")
        doc_text = f"Doctor name is Doctor {doctor}"
        resp = get_openai_response(doc_text + '\n' + prompt + '\n' + report_data)
        #st.write("🐾 Pet health summary prepared")
        st.write("Your health summary prepared")
        out_pdf = f"reports/summaries/{base_name}_summary.pdf"
        status.update(label="Rendering summary PDF…")
        resp = cleanAIResp(resp)
        #text_to_pdf_rich_chrome(resp, out_pdf, title="Pet Health Summary",
        #    doctor=doctor,
        #    lab=lab,
        #    logo_url=logo_url)
        #st.write("🖨️ PDF saved")

        text_to_pdf_rich_chrome(resp, out_pdf, title="Health Summary",
            doctor=doctor,
            lab=lab,
            logo_url=logo_url)
        st.write("🖨️ PDF saved")
        status.update(label="pdf saved")
        #print('Response from AI : ', resp)