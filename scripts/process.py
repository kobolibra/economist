#!/usr/bin/env python3
import os
import sys
import zipfile
import shutil
import re
from datetime import datetime
from bs4 import BeautifulSoup

def main():
    print("=" * 50)
    print("Starting EPUB processing...")
    print("=" * 50)
    
    # 清理
    if os.path.exists('output'):
        shutil.rmtree('output')
    if os.path.exists('temp_epub'):
        shutil.rmtree('temp_epub')
    
    os.makedirs('output/articles', exist_ok=True)
    os.makedirs('output/images', exist_ok=True)
    
    # 解压
    print("Extracting EPUB...")
    with zipfile.ZipFile('input/economist.epub', 'r') as z:
        z.extractall('temp_epub')
    
    # 复制图片
    copy_images('temp_epub', 'output/images')
    
    # 解析所有 HTML 文件
    all_articles = []
    html_files = []
    
    for root, dirs, files in os.walk('temp_epub'):
        for f in files:
            if f.endswith(('.html', '.xhtml', '.htm')):
                filepath = os.path.join(root, f)
                # 跳过导航文件
                if 'nav' in f.lower() or 'toc' in f.lower() or 'cover' in f.lower():
                    continue
                html_files.append(filepath)
    
    print(f"\nFound {len(html_files)} HTML files to process")
    
    for filepath in sorted(html_files):
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 检查是否是文章文件（包含特定标记）
            if 'downloaded by zlibrary' not in content and 'The Economist' not in content:
                continue
            
            articles = parse_html_file(content, filepath)
            all_articles.extend(articles)
            
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
    
    print(f"\nTotal articles extracted: {len(all_articles)}")
    
    if not all_articles:
        print("ERROR: No articles found!")
        sys.exit(1)
    
    # 生成网站
    generate_index(all_articles)
    generate_rss(all_articles)
    
    # 清理
    shutil.rmtree('temp_epub')
    print(f"\nSuccess! Generated {len(all_articles)} articles")

def copy_images(source_dir, output_dir):
    """复制图片"""
    for root, dirs, files in os.walk(source_dir):
        if 'images' in root.lower():
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp')):
                    src = os.path.join(root, f)
                    dst = os.path.join(output_dir, f)
                    shutil.copy2(src, dst)

def parse_html_file(html_content, source_file):
    """解析 HTML 文件，提取文章"""
    articles = []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 移除 script 和 style
    for tag in soup(['script', 'style']):
        tag.decompose()
    
    # 找文章标题 - 通常在 h1 或 h2
    title = None
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(strip=True)
    
    if not title:
        h2 = soup.find('h2')
        if h2:
            title = h2.get_text(strip=True)
    
    if not title:
        # 尝试从文件名或内容推断
        title = "Untitled Article"
    
    # 找日期 - 通常在 h3 或特定 class
    date = ""
    h3 = soup.find('h3')
    if h3:
        date = h3.get_text(strip=True)
    
    # 获取正文内容
    body = soup.find('body')
    if not body:
        return articles
    
    # 清理内容
    content_html = str(body)
    
    # 移除 body 标签本身
    content_html = re.sub(r'</?body[^>]*>', '', content_html)
    
    # 修复图片路径
    content_html = re.sub(r'src=["\']static_images/', 'src="/images/', content_html)
    content_html = re.sub(r'src=["\']../static_images/', 'src="/images/', content_html)
    
    # 如果内容太短，可能不是文章
    text_content = soup.get_text(strip=True)
    if len(text_content) < 500:
        return articles
    
    # 生成 slug
    slug = create_slug(title)
    
    # 保存文章
    art_path = f'articles/{slug}.html'
    
    html_output = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title} | The Economist</title>
    <style>
        body {{
            max-width: 720px;
            margin: 0 auto;
            padding: 40px 20px;
            font-family: Georgia, "Times New Roman", serif;
            font-size: 18px;
            line-height: 1.6;
            color: #222;
        }}
        h1 {{
            font-size: 32px;
            margin: 0 0 10px 0;
            line-height: 1.2;
            font-weight: normal;
        }}
        h2 {{
            font-size: 24px;
            margin: 30px 0 15px 0;
            font-weight: normal;
        }}
        h3 {{
            font-size: 18px;
            color: #666;
            margin: 0 0 30px 0;
            padding-bottom: 20px;
            border-bottom: 1px solid #ddd;
        }}
        p {{
            margin: 0 0 1em 0;
            text-align: justify;
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 20px auto;
        }}
        a {{
            color: #e3120b;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    {content_html}
</body>
</html>'''
    
    with open(f'output/{art_path}', 'w', encoding='utf-8') as f:
        f.write(html_output)
    
    print(f"  ✓ {title[:60]}...")
    
    articles.append({
        'title': title,
        'slug': slug,
        'path': art_path,
        'date': datetime.now().isoformat()
    })
    
    return articles

def create_slug(title):
    """生成 URL slug"""
    slug = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '-').lower()[:50]
    slug = re.sub(r'-+', '-', slug)
    # 确保唯一
    base_slug = slug
    counter = 1
    while os.path.exists(f'output/articles/{slug}.html'):
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug

def generate_index(articles):
    """生成索引页"""
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>The Economist Weekly</title>
    <style>
        body {{
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #e3120b;
            margin-bottom: 8px;
        }}
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
        }}
        .article {{
            border-bottom: 1px solid #eee;
            padding: 15px 0;
        }}
        .article:hover {{
            background: #fafafa;
            margin: 0 -40px;
            padding-left: 40px;
            padding-right: 40px;
        }}
        .article a {{
            color: #222;
            text-decoration: none;
            font-size: 17px;
            font-weight: 500;
            display: block;
        }}
        .article a:hover {{
            color: #e3120b;
        }}
        .rss {{
            display: inline-block;
            margin-top: 30px;
            padding: 12px 24px;
            background: #e3120b;
            color: white;
            text-decoration: none;
            border-radius: 6px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>The Economist</h1>
        <div class="subtitle">{len(articles)} articles • Updated {datetime.now().strftime("%Y-%m-%d")}</div>
'''
    
    for art in articles:
        html += f'''
        <div class="article">
            <a href="{art["path"]}">{art["title"]}</a>
        </div>'''
    
    html += f'''
        <a href="feed.xml" class="rss">📡 Subscribe via RSS</a>
    </div>
</body>
</html>'''
    
    with open('output/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

def generate_rss(articles):
    """生成 RSS"""
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    username, repo_name = repo.split('/')
    base_url = f"https://{username}.github.io/{repo_name}"
    
    items = []
    for art in articles[:20]:
        try:
            with open(f'output/{art["path"]}', 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取 body
            match = re.search(r'<body>(.*?)</body>', content, re.DOTALL)
            body = match.group(1) if match else content
            
            items.append(f'''
    <item>
      <title><![CDATA[{art["title"]}]]></title>
      <link>{base_url}/{art["path"]}</link>
      <guid>{base_url}/{art["path"]}</guid>
      <description><![CDATA[{art["title"]}]]></description>
      <content:encoded xmlns:content="http://purl.org/rss/1.0/modules/content/">
        <![CDATA[{body}]]>
      </content:encoded>
    </item>''')
        except Exception as e:
            print(f"Warning: RSS error for {art['title']}: {e}")
    
    rss = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/" version="2.0">
  <channel>
    <title>The Economist Weekly</title>
    <link>{base_url}/</link>
    <description>Full-text articles from The Economist</description>
    <language>en</language>
    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>
    {''.join(items)}
  </channel>
</rss>'''
    
    with open('output/feed.xml', 'w', encoding='utf-8') as f:
        f.write(rss)
    
    print(f"RSS: {base_url}/feed.xml")

if __name__ == '__main__':
    main()
