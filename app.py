"""
Globe News Frontend - Ultra-Fast Version
With Persistent Caching & Minimal Backend Calls
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import html
import re
import os
import logging
import time
import json
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Backend API configuration
BACKEND_URL = os.environ.get('BACKEND_URL', 'https://globenew--backend-api--5pt6gkpwq49b.code.run')
API_VERSION = "v1"

# ==================== PERSISTENT CACHE ====================
# Cache directory in /tmp (Vercel allows writing to /tmp)
CACHE_DIR = '/tmp/globe_news_cache'
os.makedirs(CACHE_DIR, exist_ok=True)

CACHE_TTL = {
    'articles': 300,      # 5 minutes
    'categories': 3600,   # 1 hour
    'breaking': 120,      # 2 minutes
    'movies': 600,        # 10 minutes
    'index': 60,          # 1 minute for full page cache
}

def get_cache_path(key):
    """Get file path for cache key"""
    safe_key = re.sub(r'[^a-zA-Z0-9]', '_', key)
    return os.path.join(CACHE_DIR, f"{safe_key}.json")

def get_cached(key, ttl_key='articles'):
    """Get from persistent cache"""
    cache_path = get_cache_path(key)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
                cache_time = data.get('_cache_time', 0)
                if time.time() - cache_time < CACHE_TTL.get(ttl_key, 300):
                    logger.info(f"Cache hit: {key}")
                    return data.get('_data')
        except Exception as e:
            logger.error(f"Cache read error: {e}")
    return None

def set_cached(key, data, ttl_key='articles'):
    """Save to persistent cache"""
    cache_path = get_cache_path(key)
    try:
        with open(cache_path, 'w') as f:
            json.dump({
                '_cache_time': time.time(),
                '_data': data
            }, f)
        logger.info(f"Cached: {key}")
    except Exception as e:
        logger.error(f"Cache write error: {e}")

# ==================== OPTIMIZED SESSION ====================
session = requests.Session()
retry_strategy = Retry(
    total=1,
    backoff_factor=0.3,
    status_forcelist=[500, 502, 503, 504],
)
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=40, max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# ==================== TEMPLATE FILTERS ====================

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%b %d, %Y'):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.strftime(format)
    except:
        return value[:10] if value else ""

@app.template_filter('truncate')
def truncate(text, length=150):
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    if len(text) <= length:
        return text
    return text[:length] + "..."

@app.template_filter('time_ago')
def time_ago(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        diff = datetime.now() - dt
        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}m ago"
        return "just now"
    except:
        return ""

@app.template_filter('category_color')
def category_color(category):
    colors = {
        'World': '#3b82f6', 'Technology': '#8b5cf6', 'Business': '#10b981',
        'Science': '#06b6d4', 'Health': '#ec4899', 'Sports': '#f97316',
        'Entertainment': '#ef4444', 'Politics': '#6b7280', 'General': '#6366f1'
    }
    return colors.get(category, '#6366f1')

@app.template_filter('category_icon')
def category_icon(category):
    icons = {
        'World': '🌍', 'Technology': '💻', 'Business': '📈', 'Science': '🔬',
        'Health': '🏥', 'Sports': '⚽', 'Entertainment': '🎬', 'Politics': '🏛️', 'General': '📰'
    }
    return icons.get(category, '📄')

# ==================== FAST API FUNCTIONS ====================

def fast_fetch(url, params=None, timeout=5):
    """Ultra-fast fetch with short timeout"""
    try:
        response = session.get(url, params=params, timeout=timeout)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.warning(f"Fast fetch failed: {url[:50]}... - {e}")
    return None

def fetch_articles_fast(params=None):
    """Fetch articles with aggressive caching"""
    cache_key = f"articles_{hash(str(params)) if params else 'default'}"
    
    # Try cache first
    cached = get_cached(cache_key, 'articles')
    if cached:
        return cached
    
    # Fetch from backend with short timeout
    url = f"{BACKEND_URL}/api/{API_VERSION}/articles"
    data = fast_fetch(url, params, timeout=6)
    
    if data and data.get('articles'):
        set_cached(cache_key, data, 'articles')
        return data
    
    # Return last resort data if available
    return {"articles": [], "total": 0}

def fetch_categories_fast():
    """Fetch categories with long cache"""
    cached = get_cached('categories', 'categories')
    if cached:
        return cached
    
    url = f"{BACKEND_URL}/api/{API_VERSION}/categories"
    data = fast_fetch(url, timeout=5)
    
    if data:
        set_cached('categories', data, 'categories')
        return data
    return []

def fetch_breaking_fast():
    """Fetch breaking news with short cache"""
    cached = get_cached('breaking', 'breaking')
    if cached:
        return cached
    
    url = f"{BACKEND_URL}/api/{API_VERSION}/articles/breaking/"
    data = fast_fetch(url, {"limit": 5}, timeout=5)
    
    if data:
        set_cached('breaking', data, 'breaking')
        return data
    return {"articles": []}

def fetch_movies_fast():
    """Fetch movies with long cache"""
    cached = get_cached('movies', 'movies')
    if cached:
        return cached
    
    url = f"{BACKEND_URL}/api/{API_VERSION}/movies/trending"
    data = fast_fetch(url, {"limit": 6}, timeout=6)
    
    if data:
        set_cached('movies', data, 'movies')
        return data
    return {"movies": []}

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Homepage - Ultra-fast with parallel caching"""
    language = request.args.get('language', 'all')
    page = request.args.get('page', 1, type=int)
    limit = 60
    skip = (page - 1) * limit
    
    # Try to get full page from cache (for non-logged-in users)
    full_page_cache_key = f"full_page_{language}_{page}"
    full_page_cached = get_cached(full_page_cache_key, 'index')
    if full_page_cached:
        logger.info("Serving full page from cache")
        return full_page_cached
    
    # Fetch all data in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_articles = executor.submit(fetch_articles_fast, {
            'limit': limit, 'skip': skip, 'language': language
        })
        future_breaking = executor.submit(fetch_breaking_fast)
        future_categories = executor.submit(fetch_categories_fast)
        future_movies = executor.submit(fetch_movies_fast)
        
        articles_data = future_articles.result(timeout=8)
        breaking_data = future_breaking.result(timeout=5)
        categories = future_categories.result(timeout=5)
        movies_data = future_movies.result(timeout=6)
    
    articles = articles_data.get('articles', [])
    total_articles = articles_data.get('total', 0)
    total_pages = max(1, (total_articles + limit - 1) // limit) if total_articles > 0 else 1
    breaking_articles = breaking_data.get('articles', [])[:5]
    trending_movies = movies_data.get('movies', [])
    
    # Add article counts to categories
    for category in categories:
        category['article_count'] = total_articles // max(len(categories), 1)
    
    # Render template
    rendered = render_template(
        'index.html',
        articles=articles,
        breaking_articles=breaking_articles,
        categories=categories,
        trending_movies=trending_movies,
        language=language,
        page=page,
        total_pages=total_pages,
        total_articles=total_articles,
        limit=limit
    )
    
    # Cache the full rendered page
    set_cached(full_page_cache_key, rendered, 'index')
    
    return rendered

@app.route('/article/<int:article_id>')
def article_detail(article_id):
    """Article detail page with caching"""
    # Check if article is cached
    cache_key = f"article_{article_id}"
    cached = get_cached(cache_key, 'articles')
    if cached:
        return cached
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles/{article_id}"
        article = fast_fetch(url, timeout=8)
        
        if not article:
            return render_template('error.html', message="Article not found", error_code=404), 404
        
        # Ensure all fields exist
        article.setdefault('human_summary', None)
        article.setdefault('preview_content', None)
        article.setdefault('full_content', None)
        article.setdefault('category_name', 'General')
        
        # Fetch preview if needed
        preview_html = article.get('human_summary') or article.get('preview_content')
        preview_type = 'human' if article.get('human_summary') else ('smart' if preview_html else None)
        
        # Get preview from API if not available
        if not preview_html:
            preview_url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}"
            preview_data = fast_fetch(preview_url, timeout=6)
            if preview_data and preview_data.get('has_preview'):
                preview_html = preview_data.get('preview')
                preview_type = 'smart'
        
        has_full_content = article.get('has_full_content', False)
        content_length = article.get('content_length', 0)
        needs_regeneration = not preview_html and not article.get('human_summary')
        content_warning = "⚠️ Limited content available" if not has_full_content and content_length < 500 else None
        
        rendered = render_template(
            'article_detail.html',
            article=article,
            preview_html=preview_html,
            preview_type=preview_type,
            needs_regeneration=needs_regeneration,
            has_full_content=has_full_content,
            content_warning=content_warning,
            content_length=content_length
        )
        
        # Cache the rendered article (30 minutes)
        set_cached(cache_key, rendered, 'articles')
        
        return rendered
        
    except Exception as e:
        logger.error(f"Error in article_detail: {e}")
        return render_template('error.html', message="Error loading article", error_code=500), 500

@app.route('/article/<int:article_id>/regenerate-preview')
def regenerate_preview(article_id):
    """Regenerate preview"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}/generate"
        session.post(url, timeout=15)
    except:
        pass
    # Clear article cache
    cache_key = f"article_{article_id}"
    cache_path = get_cache_path(cache_key)
    if os.path.exists(cache_path):
        os.remove(cache_path)
    return redirect(url_for('article_detail', article_id=article_id))

@app.route('/categories')
def categories():
    """Categories page with caching"""
    cached = get_cached('categories_page', 'categories')
    if cached:
        return cached
    
    categories_list = fetch_categories_fast()
    for category in categories_list:
        category['article_count'] = 1000  # Placeholder
    
    rendered = render_template('categories.html', categories=categories_list)
    set_cached('categories_page', rendered, 'categories')
    return rendered

@app.route('/category/<category_name>')
def category_detail(category_name):
    """Category detail with caching"""
    language = request.args.get('language', 'all')
    page = request.args.get('page', 1, type=int)
    cache_key = f"category_{category_name}_{language}_{page}"
    
    cached = get_cached(cache_key, 'articles')
    if cached:
        return cached
    
    limit = 20
    skip = (page - 1) * limit
    
    articles_data = fetch_articles_fast({
        'category': category_name, 'language': language, 'limit': limit, 'skip': skip
    })
    articles = articles_data.get('articles', [])
    total = articles_data.get('total', 0)
    total_pages = max(1, (total + limit - 1) // limit) if total > 0 else 1
    
    categories_list = fetch_categories_fast()
    current_category = next((c for c in categories_list if c['name'].lower() == category_name.lower()), None)
    
    if not current_category:
        return render_template('error.html', message="Category not found", error_code=404), 404
    
    rendered = render_template(
        'category_detail.html',
        category=current_category,
        articles=articles,
        language=language,
        page=page,
        total_pages=total_pages,
        total_articles=total
    )
    
    set_cached(cache_key, rendered, 'articles')
    return rendered

@app.route('/breaking')
def breaking_news():
    """Breaking news page"""
    breaking_data = fetch_breaking_fast()
    articles = breaking_data.get('articles', [])
    sources = list(set(a.get('source', 'Unknown') for a in articles))
    
    return render_template(
        'breaking.html',
        articles=articles,
        sources=sources,
        article_count=len(articles),
        source_count=len(sources)
    )

@app.route('/search')
def search():
    """Search page (no caching for search)"""
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('index'))
    
    articles_data = fetch_articles_fast({'search': query, 'limit': 20})
    articles = articles_data.get('articles', [])
    total = articles_data.get('total', 0)
    
    return render_template(
        'search.html',
        query=query,
        articles=articles,
        total_results=total
    )

# ==================== MOVIE ROUTES ====================

@app.route('/movies')
def movies_home():
    """Movies page with caching"""
    cached = get_cached('movies_page', 'movies')
    if cached:
        return cached
    
    movies_data = fetch_movies_fast()
    movies = movies_data.get('movies', [])
    categories = fetch_categories_fast()
    
    rendered = render_template('movies/index.html', movies=movies, categories=categories, total_movies=len(movies))
    set_cached('movies_page', rendered, 'movies')
    return rendered

@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    """Movie detail with caching"""
    cache_key = f"movie_{movie_id}"
    cached = get_cached(cache_key, 'movies')
    if cached:
        return cached
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/{movie_id}"
        movie = fast_fetch(url, timeout=8)
        
        if not movie:
            return render_template('error.html', message="Movie not found", error_code=404), 404
        
        rendered = render_template('movies/detail.html', movie=movie)
        set_cached(cache_key, rendered, 'movies')
        return rendered
    except Exception as e:
        logger.error(f"Error fetching movie: {e}")
        return render_template('error.html', message="Error loading movie", error_code=500), 500

@app.route('/movies/search')
def movies_search():
    """Search movies"""
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('movies_home'))
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/search"
        results = fast_fetch(url, {'query': query}, timeout=8) or {"results": []}
        movies = results.get('results', [])
        return render_template('movies/search.html', query=query, movies=movies, total_results=len(movies))
    except:
        return render_template('movies/search.html', query=query, movies=[], total_results=0)

# ==================== STATIC ROUTES ====================

@app.route('/fetch-now', methods=['POST'])
def fetch_now():
    """Clear cache and trigger fetch"""
    # Clear all cache
    for f in os.listdir(CACHE_DIR):
        os.remove(os.path.join(CACHE_DIR, f))
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/fetcher/fetch-now"
        session.post(url, timeout=10)
    except:
        pass
    
    return redirect(url_for('index'))

@app.route('/api/health')
def api_health():
    return jsonify({"frontend": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    return render_template('contact.html', success=False)

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', message="Page not found", error_code=404), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', message="Internal server error", error_code=500), 500

# ==================== SEO ROUTES ====================

@app.route('/sitemap.xml')
def sitemap():
    from flask import Response
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://globe-news-jade.vercel.app/</loc><changefreq>hourly</changefreq><priority>1.0</priority></url>
  <url><loc>https://globe-news-jade.vercel.app/breaking</loc><changefreq>hourly</changefreq><priority>0.9</priority></url>
  <url><loc>https://globe-news-jade.vercel.app/categories</loc><changefreq>daily</changefreq><priority>0.8</priority></url>
  <url><loc>https://globe-news-jade.vercel.app/movies</loc><changefreq>daily</changefreq><priority>0.8</priority></url>
</urlset>'''
    return Response(xml, mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    from flask import Response
    return Response("User-agent: *\nAllow: /\nSitemap: https://globe-news-jade.vercel.app/sitemap.xml", mimetype='text/plain')

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌐 GLOBE NEWS - ULTRA-FAST VERSION")
    print("="*60)
    print(f"🔗 Backend: {BACKEND_URL}")
    print(f"📊 Cache Directory: {CACHE_DIR}")
    print("="*60)
    
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=False,
        threaded=True
    )
