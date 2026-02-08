#!/usr/bin/env python3
import os
import sys
import zipfile
import shutil
import re
from datetime import datetime

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
    
    # 列出所有文件看结构
    print("\nEPUB structure:")
    for root, dirs, files in os.walk('temp_epub'):
        level = root.replace('temp_epub', '').count(os.sep)
        indent = ' ' * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = ' ' * 2 * (level + 1)
        for f in sorted(files)[:10]:  # 只显示前10个
            filepath = os.path.join(root, f)
            size = os.path.getsize(filepath)
            print(f"{subindent}{f} ({size} bytes)")
        if len(files) > 10:
            print(f"{subindent}... and {len(files)-10} more files")
    
    # 找所有 HTML 文件，不管大小
    html_files = []
    for root, dirs, files in os.walk('temp_epub'):
        for f in files:
            if f.endswith(('.html', '.xhtml', '.htm', '.txt')):
                filepath = os.path.join(root, f)
                size = os.path.getsize(filepath)
                html_files.append((filepath, size))
    
    print(f"\nFound {len(html_files)} HTML/text files")
    
    # 逐个检查，找包含文章内容的
    all_articles = []
    for filepath, size in sorted(html_files, key=lambda x: x[1], reverse=True):
        print(f"\nChecking: {os.path.basename(filepath)} ({size} bytes)")
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 检查是否包含 Economist 文章特征
            if 'The Economist' in content or 'static_images' in content or 'downloaded by zlibrary' in content:
                print(f"  -> Found Economist content!")
                articles = parse_content_file(content, filepath)
                all_articles.extend(articles)
                if len(articles) > 0:
                    print(f"  -> Extracted {len(articles)} articles")
                    break  # 找到主文件就停止
        except Exception as e:
            print(f"  -> Error: {e}")
    
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

def parse_content_file(content, source_file):
    """解析文章内容"""
    articles = []
    
    # 这个 EPUB 是 Markdown 格式，用 # 分隔
    # 模式：# Section\n## Title\n### Date\nContent
    
    # 先按 # 开头分割
    sections = re.split(r'\n(?=#)', content)
    
    current_section = ""
    i = 0
    
    while i < len(sections):
        section = sections[i].strip()
        if not section:
            i += 1
            continue
        
        # 一级标题：栏目（如 # Leaders）
        if section.startswith('# ') and not section.startswith('## '):
            current_section = section.split('\n')[0].replace('# ', '').strip()
            print(f"    Section: {current_section[:50]}")
            i += 1
            continue
        
        # 二级标题：可能是文章标题
        if section.startswith('## '):
            # 收集这篇文章的所有内容
            title = section.split('\n')[0].replace('## ', '').strip()
            
            # 找下一级内容
            content_lines = []
            date = ""
            
            # 检查下一行是否是 ### 日期
            lines = section.split('\n')
            for j, line in enumerate(lines[1:], 1):
                if line.startswith('###'):
                    date = line.replace('###', '').strip()
                    content_lines = lines[j+1:]
                    break
                elif line.strip() and not content_lines:
                    # 没有日期，直接是内容
                    content_lines = lines[j:]
                    break
            
            article_content = '\n'.join(content_lines)
            
            # 清理
            article_content = clean_article_content(article_content)
            
            if len(article_content) > 200 and title:
                slug = create_slug(title)
                
                # 保存
                art_path = f'articles/{slug}.html'
                html = generate_article_html(title, date, current_section, article_content)
                
                with open(f'output/{art_path}', 'w', encoding='utf-8') as f:
                    f.write(html)
                
                articles.append({
                    'title': title,
                    'slug': slug,
                    'path': art_path,
                    'date': datetime.now().isoformat(),
                    'section': current_section
                })
                print(f"    ✓ {title[:60]}...")
        
        i += 1
    
    return articles

def clean_article_content(content):
    """清理文章内容"""
    # 移除下载来源
    content = re.sub(r'This article was downloaded by zlibrary from https?://\S+', '', content)
    
    # 转换图片 ![](path) -> <img>
    content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', r'<img src="\2" alt="\1" style="max-width:100%;"/>', content)
    
    # 转换链接 [text](url) -> <a>
    content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', content)
    
    # 转换 **bold** -> <strong>
    content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)
    
    # 转换 *italic* -> <em>
    content = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', content)
    
    # 转换换行 -> <p>
    paragraphs = content.split('\n\n')
    paragraphs = [f'<p>{p.strip()}</p>' for p in paragraphs if p.strip()]
    content = '\n'.join(paragraphs)
    
    return content.strip()

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

def generate_article_html(title, date, section, content):
    """生成文章 HTML"""
    return f'''<!DOCTYPE html>
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
        .section {{
            color: #e3120b;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        }}
        h1 {{
            font-size: 32px;
            margin: 0 0 10px 0;
            line-height: 1.2;
            font-weight: normal;
        }}
        .date {{
            color: #666;
            font-size: 14px;
            margin-bottom: 30px;
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
    <div class="section">{section or "The Economist"}</div>
    <h1>{title}</h1>
    <div class="date">{date or "Weekly Edition"}</div>
    {content}
</body>
</html>'''

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
        .section {{
            color: #e3120b;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .article a {{
            color: #222;
            text-decoration: none;
            font-size: 17px;
            font-weight: 500;
            display: block;
            margin-top: 4px;
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
            <div class="section">{art.get("section", "")}</div>
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
      <description><![CDATA[{art["title"]} - {art.get("section", "The Economist")}]]></description>
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
