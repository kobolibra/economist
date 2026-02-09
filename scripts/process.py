#!/usr/bin/env python3
import os
import sys
import zipfile
import shutil
import re
from datetime import datetime
from bs4 import BeautifulSoup

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

def normalize_section(text):
    t = text.lower()
    for s in ALLOWED_SECTIONS:
        if s.lower() in t:
            return s
    return None

def main():
    print("=" * 50)
    print("Starting EPUB processing...")
    print("=" * 50)
    
    shutil.rmtree('output', ignore_errors=True)
    shutil.rmtree('temp_epub', ignore_errors=True)
    
    os.makedirs('output/articles', exist_ok=True)
    os.makedirs('output/images', exist_ok=True)
    
    with zipfile.ZipFile('input/economist.epub', 'r') as z:
        z.extractall('temp_epub')
    
    copy_images('temp_epub', 'output/images')
    
    spine_files = get_spine_order('temp_epub')
    
    all_articles = []
    
    for filepath in spine_files:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                html = f.read()
            articles = parse_html_file(html)
            all_articles.extend(articles)
        except Exception as e:
            print("Error:", e)
    
    print("Articles:", len(all_articles))
    
    generate_index(all_articles)
    print("Done.")

def parse_html_file(html):
    soup = BeautifulSoup(html, 'html.parser')
    body = soup.find('body')
    if not body:
        return []
    
    articles = []
    
    h1s = body.find_all('h1')
    
    for h1 in h1s:
        title = h1.get_text(strip=True)
        
        # section 判断
        section = None
        prev = h1.find_previous(['h2','h3'])
        if prev:
            section = normalize_section(prev.get_text(strip=True))
        
        if not section:
            continue
        
        content_nodes = []
        
        for sib in h1.next_siblings:
            if getattr(sib, "name", None) == "h1":
                break
            content_nodes.append(str(sib))
        
        content_html = "".join(content_nodes)
        
        # 修复图片路径
        content_html = re.sub(
            r'src=["\']([^"\']*?/)?([^/"\']+\.(jpg|jpeg|png|gif|svg|webp))["\']',
            r'src="../images/\2"',
            content_html,
            flags=re.IGNORECASE
        )
        
        article = create_article(title, section, content_html)
        if article:
            articles.append(article)
    
    return articles

def create_article(title, section, content):
    if len(content) < 200:
        return None
    
    slug = re.sub(r'[^\w\s-]', '', title).replace(' ', '-').lower()[:60]
    
    path = f'articles/{slug}.html'
    
    html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body>
<div>{section}</div>
<h1>{title}</h1>
{content}
</body>
</html>'''
    
    with open(f'output/{path}', 'w', encoding='utf-8') as f:
        f.write(html)
    
    return {"title": title, "path": path, "section": section}

def copy_images(src, dst):
    for r,_,files in os.walk(src):
        for f in files:
            if f.lower().endswith(('.jpg','.jpeg','.png','.gif','.svg','.webp')):
                s = os.path.join(r,f)
                d = os.path.join(dst,f)
                if not os.path.exists(d):
                    shutil.copy2(s,d)

def generate_index(articles):
    html = "<html><body>"
    current = None
    for a in articles:
        if a["section"] != current:
            current = a["section"]
            html += f"<h2>{current}</h2>"
        html += f'<div><a href="{a["path"]}">{a["title"]}</a></div>'
    html += "</body></html>"
    
    with open('output/index.html','w',encoding='utf-8') as f:
        f.write(html)

def get_spine_order(root):
    files = []
    for r,_,fs in os.walk(root):
        for f in fs:
            if f.endswith(('.html','.xhtml')):
                files.append(os.path.join(r,f))
    files.sort()
    return files

if __name__ == '__main__':
    main()
