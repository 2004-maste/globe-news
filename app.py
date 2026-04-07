"""
Globe News Frontend - Complete Version
Optimized for Speed with Aggressive Caching & Parallel Requests
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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Backend API configuration
BACKEND_URL = os.environ.get('BACKEND_URL', 'https://globenew--backend-api--5pt6gkpwq49b.code.run')
API_VERSION = "v1"

# Optimized timeouts
DEFAULT_TIMEOUT = 8  # Reduced from 30 to 8 seconds
LONG_TIMEOUT = 15

# Create a session with connection pooling and retries
session = requests.Session()
retry_strategy = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
)
adapter = HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# ==================== AGGRESSIVE CACHING ====================
# In-memory cache with longer TTL
cache = {}
CACHE_TTL = {
    'articles': 300,      # 5 minutes
    'categories': 3600,   # 1 hour
    'breaking': 120,      # 2 minutes
    'movies': 600,        # 10 minutes
}

def get_cache_key(prefix, params=None):
    """Generate cache key"""
    if params:
        return f"{prefix}_{hash(frozenset(params.items()))}"
    return prefix

def get_cached(key, ttl_key='articles'):
    """Get from cache"""
    if key in cache:
        data, timestamp = cache[key]
        if time.time() - timestamp < CACHE_TTL.get(ttl_key, 300):
            return data
    return None

def set_cached(key, data, ttl_key='articles'):
    """Set cache"""
    cache[key] = (data, time.time())

# ==================== TEMPLATE FILTERS ====================

@app.template_filter('datetimeformat')
def datetimeformat(value, format='%b %d, %Y %H:%M'):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.strftime(format)
    except:
        return value

@app.template_filter('truncate')
def truncate(text, length=200):
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[:length] + "..."

@app.template_filter('time_ago')
def time_ago(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years}y ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months}mo ago"
        elif diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}h ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        else:
            return "just now"
    except:
        return value

@app.template_filter('category_color')
def category_color(category):
    colors = {
        'World': '#3b82f6',
        'Technology': '#8b5cf6',
        'Business': '#10b981',
        'Science': '#06b6d4',
        'Health': '#ec4899',
        'Sports': '#f97316',
        'Entertainment': '#ef4444',
        'Politics': '#6b7280',
        'General': '#6366f1'
    }
    return colors.get(category, '#6366f1')

@app.template_filter('category_icon')
def category_icon(category):
    icons = {
        'World': '🌍',
        'Technology': '💻',
        'Business': '📈',
        'Science': '🔬',
        'Health': '🏥',
        'Sports': '⚽',
        'Entertainment': '🎬',
        'Politics': '🏛️',
        'General': '📰'
    }
    return icons.get(category, '📄')

# ==================== OPTIMIZED API HELPER FUNCTIONS ====================

def fetch_with_session(url, params=None, timeout=DEFAULT_TIMEOUT):
    """Make request with session and timeout"""
    try:
        response = session.get(url, params=params, timeout=timeout)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Request failed: {url} - {e}")
        return None

def fetch_articles(params=None):
    """Fetch articles with caching"""
    cache_key = get_cache_key('articles', params)
    cached = get_cached(cache_key, 'articles')
    if cached:
        logger.info(f"Using cached articles")
        return cached
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles"
        data = fetch_with_session(url, params, DEFAULT_TIMEOUT)
        if data:
            set_cached(cache_key, data, 'articles')
            return data
        return {"articles": [], "total": 0}
    except Exception as e:
        logger.error(f"Error fetching articles: {e}")
        return {"articles": [], "total": 0}

def fetch_article(article_id):
    """Fetch single article"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles/{article_id}"
        data = fetch_with_session(url, timeout=DEFAULT_TIMEOUT)
        if data:
            if 'human_summary' not in data:
                data['human_summary'] = None
            if 'preview_content' not in data:
                data['preview_content'] = None
            if 'full_content' not in data:
                data['full_content'] = None
            if 'category_name' not in data:
                data['category_name'] = 'General'
        return data
    except Exception as e:
        logger.error(f"Error fetching article {article_id}: {e}")
        return None

def fetch_categories():
    """Fetch categories with long cache"""
    cached = get_cached('categories', 'categories')
    if cached:
        return cached
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/categories"
        data = fetch_with_session(url, timeout=DEFAULT_TIMEOUT)
        if data:
            set_cached('categories', data, 'categories')
            return data
        return []
    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return []

def fetch_breaking_articles():
    """Fetch breaking news with short cache"""
    cached = get_cached('breaking', 'breaking')
    if cached:
        return cached
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles/breaking/"
        data = fetch_with_session(url, {"limit": 10}, DEFAULT_TIMEOUT)
        if data:
            set_cached('breaking', data, 'breaking')
            return data
        return {"articles": []}
    except Exception as e:
        logger.error(f"Error fetching breaking articles: {e}")
        return {"articles": []}

def fetch_trending_movies(media_type='all', limit=20):
    """Fetch trending movies with long cache"""
    cache_key = f"movies_{media_type}_{limit}"
    cached = get_cached(cache_key, 'movies')
    if cached:
        return cached
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/trending"
        data = fetch_with_session(url, {'media_type': media_type, 'limit': limit}, DEFAULT_TIMEOUT)
        if data:
            set_cached(cache_key, data, 'movies')
            return data
        return {"movies": [], "count": 0}
    except Exception as e:
        logger.error(f"Error fetching trending movies: {e}")
        return {"movies": [], "count": 0}

def fetch_preview(article_id):
    """Fetch content preview"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}"
        return fetch_with_session(url, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        logger.error(f"Error fetching preview for article {article_id}: {e}")
        return None

def generate_preview(article_id):
    """Generate new preview"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}/generate"
        response = session.post(url, timeout=LONG_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        return None

def trigger_fetch():
    """Trigger manual news fetch"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/fetcher/fetch-now"
        response = session.post(url, timeout=LONG_TIMEOUT)
        if response.status_code == 200:
            return response.json()
        return {"message": "Error triggering fetch"}
    except Exception as e:
        logger.error(f"Error triggering fetch: {e}")
        return {"message": "Error triggering fetch"}

def fetch_movie_details(movie_id):
    """Fetch single movie details"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/{movie_id}"
        return fetch_with_session(url, timeout=DEFAULT_TIMEOUT)
    except Exception as e:
        logger.error(f"Error fetching movie {movie_id}: {e}")
        return None

def search_movies(query):
    """Search for movies"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/search"
        return fetch_with_session(url, {'query': query}, DEFAULT_TIMEOUT) or {"results": [], "count": 0}
    except Exception as e:
        logger.error(f"Error searching movies: {e}")
        return {"results": [], "count": 0}

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Homepage - Optimized with parallel requests"""
    language = request.args.get('language', 'all')
    page = request.args.get('page', 1, type=int)
    limit = 60
    skip = (page - 1) * limit
    
    # Use ThreadPoolExecutor for parallel API calls
    results = {}
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all fetch tasks in parallel
        future_articles = executor.submit(fetch_articles, {
            'limit': limit, 
            'skip': skip,
            'language': language
        })
        future_breaking = executor.submit(fetch_breaking_articles)
        future_categories = executor.submit(fetch_categories)
        future_movies = executor.submit(fetch_trending_movies, 'all', 6)
        
        # Collect results with timeouts
        try:
            articles_data = future_articles.result(timeout=10)
        except:
            articles_data = {"articles": [], "total": 0}
        
        try:
            breaking_data = future_breaking.result(timeout=8)
        except:
            breaking_data = {"articles": []}
        
        try:
            categories = future_categories.result(timeout=8)
        except:
            categories = []
        
        try:
            trending_movies_data = future_movies.result(timeout=8)
        except:
            trending_movies_data = {"movies": [], "count": 0}
    
    articles = articles_data.get('articles', [])
    total_articles = articles_data.get('total', 0)
    total_pages = (total_articles + limit - 1) // limit if total_articles > 0 else 1
    breaking_articles = breaking_data.get('articles', [])[:5]
    trending_movies = trending_movies_data.get('movies', [])
    
    # Get article counts for categories (simplified to avoid extra calls)
    for category in categories:
        category['article_count'] = total_articles  # Fallback, or make a separate call
    
    logger.info(f"Page loaded: {len(articles)} articles, {len(breaking_articles)} breaking, {len(trending_movies)} movies")
    
    return render_template(
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

@app.route('/article/<int:article_id>')
def article_detail(article_id):
    """Article detail page"""
    try:
        article = fetch_article(article_id)
        
        if not article:
            return render_template('error.html', 
                                 message="Article not found",
                                 error_code=404), 404
        
        preview_data = fetch_preview(article_id)
        
        has_full_content = article.get('has_full_content', False)
        content_length = article.get('content_length', 0)
        
        preview_html = None
        preview_type = None
        
        if article.get('human_summary'):
            preview_html = article['human_summary']
            preview_type = 'human'
        elif article.get('preview_content'):
            preview_html = article['preview_content']
            preview_type = 'smart'
        elif preview_data and preview_data.get('has_preview'):
            preview_html = preview_data.get('preview')
            preview_type = 'smart'
        
        needs_regeneration = False
        if preview_type == 'smart' and not preview_html:
            needs_regeneration = True
        elif not preview_html and not article.get('human_summary'):
            needs_regeneration = True
        
        content_warning = None
        if not has_full_content and content_length < 500:
            content_warning = "⚠️ Limited content available"
        
        return render_template(
            'article_detail.html',
            article=article,
            preview_html=preview_html,
            preview_type=preview_type,
            needs_regeneration=needs_regeneration,
            has_full_content=has_full_content,
            content_warning=content_warning,
            content_length=content_length
        )
        
    except Exception as e:
        logger.error(f"Error in article_detail: {e}")
        return render_template('error.html', 
                             message="An error occurred loading the article",
                             error_code=500), 500

@app.route('/article/<int:article_id>/regenerate-preview')
def regenerate_preview(article_id):
    """Regenerate preview for article"""
    result = generate_preview(article_id)
    
    if result and result.get('success'):
        return redirect(url_for('article_detail', article_id=article_id))
    else:
        article = fetch_article(article_id)
        return render_template(
            'article_detail.html',
            article=article,
            preview_html=None,
            error_message="Failed to regenerate preview. Please try again.",
            needs_regeneration=True
        )

@app.route('/categories')
def categories():
    """Categories listing page"""
    categories_list = fetch_categories()
    
    for category in categories_list:
        try:
            params = {'category': category['name'], 'limit': 1}
            data = fetch_articles(params)
            category['article_count'] = data.get('total', 0)
        except:
            category['article_count'] = 0
    
    return render_template('categories.html', categories=categories_list)

@app.route('/category/<category_name>')
def category_detail(category_name):
    """Individual category page"""
    language = request.args.get('language', 'all')
    page = request.args.get('page', 1, type=int)
    limit = 20
    skip = (page - 1) * limit
    
    params = {
        'category': category_name,
        'language': language,
        'limit': limit,
        'skip': skip
    }
    
    articles_data = fetch_articles(params)
    articles = articles_data.get('articles', [])
    total = articles_data.get('total', 0)
    total_pages = (total + limit - 1) // limit if total > 0 else 1
    
    categories_list = fetch_categories()
    current_category = next((c for c in categories_list if c['name'].lower() == category_name.lower()), None)
    
    if not current_category:
        return render_template('error.html', 
                            message="Category not found",
                            error_code=404), 404
    
    return render_template(
        'category_detail.html',
        category=current_category,
        articles=articles,
        language=language,
        page=page,
        total_pages=total_pages,
        total_articles=total
    )

@app.route('/breaking')
def breaking_news():
    """Breaking news page"""
    breaking_data = fetch_breaking_articles()
    articles = breaking_data.get('articles', [])
    sources = list(set(article.get('source', 'Unknown') for article in articles))
    
    return render_template(
        'breaking.html',
        articles=articles,
        sources=sources,
        article_count=len(articles),
        source_count=len(sources)
    )

@app.route('/search')
def search():
    """Search results page"""
    query = request.args.get('q', '')
    language = request.args.get('language', 'all')
    page = request.args.get('page', 1, type=int)
    limit = 20
    skip = (page - 1) * limit
    
    if not query:
        return redirect(url_for('index'))
    
    params = {
        'search': query,
        'language': language,
        'limit': limit,
        'skip': skip
    }
    
    articles_data = fetch_articles(params)
    articles = articles_data.get('articles', [])
    total = articles_data.get('total', 0)
    total_pages = (total + limit - 1) // limit if total > 0 else 1
    
    return render_template(
        'search.html',
        query=query,
        articles=articles,
        language=language,
        page=page,
        total_pages=total_pages,
        total_results=total
    )

# ==================== MOVIE ROUTES ====================

@app.route('/movies')
def movies_home():
    """Movies and TV Shows homepage"""
    media_type = request.args.get('type', 'all')
    limit = 40
    
    movies_data = fetch_trending_movies(media_type, limit)
    movies = movies_data.get('movies', [])
    categories = fetch_categories()
    
    return render_template(
        'movies/index.html',
        movies=movies,
        media_type=media_type,
        categories=categories,
        total_movies=movies_data.get('count', 0)
    )

@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    """Movie detail page"""
    movie = fetch_movie_details(movie_id)
    
    if not movie:
        return render_template('error.html', 
                             message="Movie not found",
                             error_code=404), 404
    
    return render_template(
        'movies/detail.html',
        movie=movie
    )

@app.route('/movies/search')
def movies_search():
    """Search movies page"""
    query = request.args.get('q', '')
    
    if not query:
        return redirect(url_for('movies_home'))
    
    results = search_movies(query)
    movies = results.get('results', [])
    
    return render_template(
        'movies/search.html',
        query=query,
        movies=movies,
        total_results=len(movies)
    )

# ==================== STATIC ROUTES ====================

@app.route('/fetch-now', methods=['POST'])
def fetch_now():
    """Trigger manual news fetch"""
    result = trigger_fetch()
    return redirect(url_for('index'))

@app.route('/api/health')
def api_health():
    """API health check"""
    try:
        response = session.get(f"{BACKEND_URL}/api/{API_VERSION}/health/status", timeout=5)
        backend_status = response.json() if response.status_code == 200 else {"status": "unreachable"}
        
        return jsonify({
            "frontend": "healthy",
            "backend": backend_status,
            "timestamp": datetime.now().isoformat()
        })
    except:
        return jsonify({
            "frontend": "healthy",
            "backend": {"status": "unreachable"},
            "timestamp": datetime.now().isoformat()
        }), 200

# ==================== STATIC PAGES ====================

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        return render_template('contact.html', success=True)
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
  <url><loc>https://globe-news-jade.vercel.app/search</loc><changefreq>monthly</changefreq><priority>0.5</priority></url>
</urlset>'''
    return Response(xml, mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    from flask import Response
    robots_txt = """User-agent: *
Allow: /
Sitemap: https://globe-news-jade.vercel.app/sitemap.xml
Disallow: /fetch-now"""
    return Response(robots_txt, mimetype='text/plain')

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌐 GLOBE NEWS FRONTEND - Starting Server (Optimized)")
    print("="*60)
    print(f"📱 Frontend: http://localhost:5000")
    print(f"🔗 Backend: {BACKEND_URL}")
    print(f"📊 Version: 3.1.0 (Optimized with Caching & Parallel Requests)")
    print("="*60)
    
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=False  # Set to False for production speed
    )
