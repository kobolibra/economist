#!/usr/bin/env python3
import os
import sys
import zipfile
import shutil
import re
from datetime import datetime
from bs4 import BeautifulSoup, NavigableString

ALLOWED_SECTIONS = [
    "Leaders",
    "By Invitation",
    "Briefing",
    "China",
    "International",
    "Business",
    "Finance & economics",
    "Science & technology",
    "Culture"
]

def normalize_section(name):
    n = name.lower().strip()
    for s in ALLOWED_SECTIONS:
        if s.lower() in n or n in s.lower():
            return s
    return None

def main():
    print("=" * 50)
    print("Starting EPUB processing...")
    print("=" * 50)
    
    if os.path.exists('output'):
        shutil.rmtree('output')
    if os.path.exists('temp_epub'):
        shutil.rmtree('temp_epub')
    
    os.makedirs('output/articles', exist_ok=True)
    os.makedirs('output/images', exist_ok=True)
    
    print("Extracting EPUB...")
    with zipfile.ZipFile('input/economist.epub', 'r') as z:
        z.extractall('temp_epub')
    
    copy_images('temp_epub', 'output/images')
    
    sections_order = ALLOWED_SECTIONS[:]
    print(f"\nUsing sections order: {sections_order}")
    
    all_articles = []
    processed_files = set()
    
    spine_files = get_spine_order('temp_epub')
    print(f"Spine files: {len(spine_files)}")
    
    for filepath in spine_files:
        if filepath in processed_files:
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            if 'The Economist' not in content and 'economist.com' not in content:
                continue
            
            articles = parse_html_file(content, filepath, sections_order)
            all_articles.extend(articles)
            processed_files.add(filepath)
            
        except Exception as e:
            print(f"Error in {os.path.basename(filepath)}: {e}")
    
    print(f"\nTotal articles: {len(all_articles)}")
    
    if not all_articles:
        print("ERROR: No articles found!")
        sys.exit(1)
    
    seen = set()
    unique_articles = []
    for art in all_articles:
        if art['slug'] not in seen:
            seen.add(art['slug'])
            unique_articles.append(art)
    
    print(f"Unique articles: {len(unique_articles)}")
    
    generate_index(unique_articles, sections_order)
    generate_rss(unique_articles)
    
    shutil.rmtree('temp_epub')
    print(f"\nSuccess! Generated {len(unique_articles)} articles")

def get_spine_order(epub_root):
    files = []
    opf_path = find_file(epub_root, '.opf')
    if opf_path:
        try:
            with open(opf_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            
            manifest = {}
            for item in root.findall('.//{http://www.idpf.org/2007/opf}item'):
                item_id = item.get('id')
                item_href = item.get('href')
                if item_id and item_href:
                    manifest[item_id] = os.path.join(os.path.dirname(opf_path), item_href)
            
            for itemref in root.findall('.//{http://www.idpf.org/2007/opf}itemref'):
                item_id = itemref.get('idref')
                if item_id in manifest:
                    files.append(manifest[item_id])
            
        except Exception as e:
            print(f"Error parsing spine: {e}")
    
    if not files:
        for root, dirs, filenames in os.walk(epub_root):
            for f in filenames:
                if f.endswith(('.html', '.xhtml', '.htm')):
                    files.append(os.path.join(root, f))
        files.sort()
    
    return files

def parse_html_file(html_content, filepath, sections_order):
    articles = []
    soup = BeautifulSoup(html_content, 'html.parser')
    
    for tag in soup(['script', 'style']):
        tag.decompose()
    
    body = soup.find('body')
    if not body:
        return articles
    
    # ✅ 修复图片路径 + 收集图片 HTML
    image_html = []
    for img in body.find_all('img'):
        src = img.get('src', '')
        filename = os.path.basename(src)
        img['src'] = f"/images/{filename}"
        image_html.append(str(img))
    
    image_block = "\n".join(image_html)
    
    full_text = body.get_text('\n', strip=True)
    
    section_pattern = r'(Leaders|By Invitation|Briefing|China|International|Business|Finance & economics|Science & technology|Culture)\s*\|\s*([^\n]+)'
    matches = list(re.finditer(section_pattern, full_text, re.IGNORECASE))
    
    for i, match in enumerate(matches):
        section_name = normalize_section(match.group(1))
        if not section_name:
            continue
        
        subtitle = match.group(2).strip()
        
        start = match.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(full_text)
        section_text = full_text[start:end]
        
        # ✅ 把图片注入内容
        section_text = image_block + "\n\n" + section_text
        
        article = parse_article_text(section_text, section_name, subtitle)
        if article:
            articles.append(article)
            print(f"  ✓ [{section_name}] {article['title'][:50]}...")
    
    return articles

def parse_article_text(text, section_name, subtitle):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return None
    
    title = ""
    date = ""
    content_start = 0
    
    for i, line in enumerate(lines):
        if line == subtitle:
            continue
        
        if re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)', line):
            date = line
            content_start = i + 1
            continue
        
        if not title and len(line) > 10 and line[0].isupper():
            title = line
            content_start = i + 1
    
    if not title:
        title = subtitle
    
    content_lines = lines[content_start:]
    content = '\n\n'.join(content_lines)
    
    if len(content) < 100:
        return None
    
    return create_article(title, date, section_name, content)

def create_article(title, date, section, content):
    title = re.sub(r'\s+', ' ', title).strip()
    slug = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()[:50]
    
    base_slug = slug
    counter = 1
    while os.path.exists(f'output/articles/{slug}.html'):
        slug = f"{base_slug}-{counter}"
        counter += 1
    
    # ✅ 如果已经包含 HTML（图片），不要转纯文本
    if '<img' not in content:
        paragraphs = content.split('\n\n')
        paragraphs = [f'<p>{p.strip()}</p>' for p in paragraphs if p.strip()]
        content = '\n'.join(paragraphs)
    
    art_path = f'articles/{slug}.html'
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body>
<div class="section">{section}</div>
<h1>{title}</h1>
<div class="date">{date}</div>
{content}
</body>
</html>'''
    
    with open(f'output/{art_path}', 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {
        'title': title,
        'slug': slug,
        'path': art_path,
        'date': datetime.now().isoformat(),
        'section': section
    }

def copy_images(source_dir, output_dir):
    for r, dirs, files in os.walk(source_dir):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
                src = os.path.join(r, f)
                dst = os.path.join(output_dir, f)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)

def generate_index(articles, sections_order):
    by_section = {s: [] for s in sections_order}
    for art in articles:
        if art['section'] in by_section:
            by_section[art['section']].append(art)
    
    html = "<html><body>"
    for sec in sections_order:
        if by_section[sec]:
            html += f"<h2>{sec}</h2>"
            for art in by_section[sec]:
                html += f'<div><a href="{art["path"]}">{art["title"]}</a></div>'
    html += "</body></html>"
    
    with open('output/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

def generate_rss(articles):
    pass

def find_file(root, filename):
    for r, d, files in os.walk(root):
        for f in files:
            if f == filename or f.endswith(filename):
                return os.path.join(r, f)
    return None

if __name__ == '__main__':
    main()
