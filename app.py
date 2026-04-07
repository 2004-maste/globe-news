"""
Globe News Frontend - Resilient Version
Always loads immediately with fallback content
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime
import requests
import os
import logging
import json
import time
from threading import Thread

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Backend API configuration
BACKEND_URL = os.environ.get('BACKEND_URL', 'https://globenew--backend-api--5pt6gkpwq49b.code.run')
API_VERSION = "v1"

# ==================== SIMPLE FILE CACHE ====================
CACHE_DIR = '/tmp/globe_cache'
os.makedirs(CACHE_DIR, exist_ok=True)

def cache_get(key):
    """Get from cache"""
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                age = time.time() - data.get('timestamp', 0)
                # Cache valid for 5 minutes
                if age < 300:
                    return data.get('value')
        except:
            pass
    return None

def cache_set(key, value):
    """Save to cache"""
    cache_file = os.path.join(CACHE_DIR, f"{key}.json")
    try:
        with open(cache_file, 'w') as f:
            json.dump({'timestamp': time.time(), 'value': value}, f)
    except:
        pass

# ==================== BACKGROUND FETCHER ====================
# Store cached data that updates in background
cached_articles = []
cached_breaking = []
cached_categories = []
cached_movies = []
cached_total = 0
last_update = 0

def background_fetch():
    """Fetch data in background thread"""
    global cached_articles, cached_breaking, cached_categories, cached_movies, cached_total, last_update
    
    while True:
        try:
            # Try to fetch articles
            try:
                url = f"{BACKEND_URL}/api/{API_VERSION}/articles?limit=60"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    cached_articles = data.get('articles', [])
                    cached_total = data.get('total', 0)
                    cache_set('articles', cached_articles)
                    cache_set('total', cached_total)
                    logger.info(f"Background: Fetched {len(cached_articles)} articles")
            except Exception as e:
                logger.warning(f"Background articles failed: {e}")
                # Use cached if available
                if not cached_articles:
                    cached_articles = cache_get('articles') or []
                    cached_total = cache_get('total') or 0
            
            # Try to fetch breaking
            try:
                url = f"{BACKEND_URL}/api/{API_VERSION}/articles/breaking/?limit=5"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    cached_breaking = resp.json().get('articles', [])
                    cache_set('breaking', cached_breaking)
                    logger.info(f"Background: Fetched {len(cached_breaking)} breaking")
            except Exception as e:
                logger.warning(f"Background breaking failed: {e}")
                if not cached_breaking:
                    cached_breaking = cache_get('breaking') or []
            
            # Try to fetch categories
            try:
                url = f"{BACKEND_URL}/api/{API_VERSION}/categories"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    cached_categories = resp.json()
                    # Add article counts
                    for cat in cached_categories:
                        cat['article_count'] = cached_total // max(len(cached_categories), 1)
                    cache_set('categories', cached_categories)
                    logger.info(f"Background: Fetched {len(cached_categories)} categories")
            except Exception as e:
                logger.warning(f"Background categories failed: {e}")
                if not cached_categories:
                    cached_categories = cache_get('categories') or []
            
            # Try to fetch movies
            try:
                url = f"{BACKEND_URL}/api/{API_VERSION}/movies/trending?limit=6"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    cached_movies = resp.json().get('movies', [])
                    cache_set('movies', cached_movies)
                    logger.info(f"Background: Fetched {len(cached_movies)} movies")
            except Exception as e:
                logger.warning(f"Background movies failed: {e}")
                if not cached_movies:
                    cached_movies = cache_get('movies') or []
            
            last_update = time.time()
            
        except Exception as e:
            logger.error(f"Background fetch error: {e}")
        
        # Wait 5 minutes before next background update
        time.sleep(300)

# Start background thread
bg_thread = Thread(target=background_fetch, daemon=True)
bg_thread.start()

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
    import re
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

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Homepage - Always loads instantly from cache"""
    language = request.args.get('language', 'all')
    page = request.args.get('page', 1, type=int)
    limit = 60
    
    # Use globally cached data (updated in background)
    articles = cached_articles
    total_articles = cached_total
    breaking_articles = cached_breaking[:5]
    categories = cached_categories
    trending_movies = cached_movies
    
    # Simple pagination for display only
    start = (page - 1) * limit
    end = start + limit
    paginated_articles = articles[start:end] if articles else []
    total_pages = max(1, (total_articles + limit - 1) // limit) if total_articles > 0 else 1
    
    # Add status indicator for first load
    show_loading = len(articles) == 0 and last_update == 0
    
    return render_template(
        'index.html',
        articles=paginated_articles,
        breaking_articles=breaking_articles,
        categories=categories,
        trending_movies=trending_movies,
        language=language,
        page=page,
        total_pages=total_pages,
        total_articles=total_articles,
        limit=limit,
        show_loading=show_loading
    )

@app.route('/article/<int:article_id>')
def article_detail(article_id):
    """Article detail - fetch on demand with cache"""
    # Try cache first
    cache_key = f"article_{article_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles/{article_id}"
        response = requests.get(url, timeout=10)
        
        if response.status_code != 200:
            return render_template('error.html', message="Article not found", error_code=404), 404
        
        article = response.json()
        
        # Set defaults
        article.setdefault('human_summary', None)
        article.setdefault('preview_content', None)
        article.setdefault('full_content', None)
        article.setdefault('category_name', 'General')
        
        # Try to get preview
        preview_html = article.get('human_summary') or article.get('preview_content')
        preview_type = 'human' if article.get('human_summary') else ('smart' if preview_html else None)
        
        if not preview_html:
            try:
                preview_url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}"
                preview_resp = requests.get(preview_url, timeout=8)
                if preview_resp.status_code == 200:
                    preview_data = preview_resp.json()
                    if preview_data.get('has_preview'):
                        preview_html = preview_data.get('preview')
                        preview_type = 'smart'
            except:
                pass
        
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
        
        # Cache for 1 hour
        cache_set(cache_key, rendered)
        
        return rendered
        
    except Exception as e:
        logger.error(f"Error in article_detail: {e}")
        return render_template('error.html', message="Error loading article", error_code=500), 500

@app.route('/article/<int:article_id>/regenerate-preview')
def regenerate_preview(article_id):
    """Regenerate preview"""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}/generate"
        requests.post(url, timeout=15)
    except:
        pass
    # Clear cache
    cache_file = os.path.join(CACHE_DIR, f"article_{article_id}.json")
    if os.path.exists(cache_file):
        os.remove(cache_file)
    return redirect(url_for('article_detail', article_id=article_id))

@app.route('/categories')
def categories():
    """Categories page"""
    categories_list = cached_categories
    return render_template('categories.html', categories=categories_list)

@app.route('/category/<category_name>')
def category_detail(category_name):
    """Category detail"""
    # Filter articles by category
    category_articles = [a for a in cached_articles if a.get('category_name', '').lower() == category_name.lower()]
    total = len(category_articles)
    
    current_category = {'name': category_name, 'description': f'{category_name} news'}
    
    return render_template(
        'category_detail.html',
        category=current_category,
        articles=category_articles[:20],
        language='all',
        page=1,
        total_pages=1,
        total_articles=total
    )

@app.route('/breaking')
def breaking_news():
    """Breaking news page"""
    return render_template('breaking.html', articles=cached_breaking[:20])

@app.route('/search')
def search():
    """Search page"""
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('index'))
    
    # Simple search in cached articles
    results = []
    query_lower = query.lower()
    for a in cached_articles:
        if query_lower in a.get('title', '').lower() or query_lower in a.get('description', '').lower():
            results.append(a)
    
    return render_template('search.html', query=query, articles=results[:20], total_results=len(results))

# ==================== MOVIE ROUTES ====================

@app.route('/movies')
def movies_home():
    """Movies page"""
    return render_template('movies/index.html', movies=cached_movies)

@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    """Movie detail"""
    # Find movie in cached list
    movie = None
    for m in cached_movies:
        if m.get('tmdb_id') == movie_id:
            movie = m
            break
    
    if not movie:
        # Try to fetch on demand
        try:
            url = f"{BACKEND_URL}/api/{API_VERSION}/movies/{movie_id}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                movie = response.json()
        except:
            pass
    
    if not movie:
        return render_template('error.html', message="Movie not found", error_code=404), 404
    
    return render_template('movies/detail.html', movie=movie)

@app.route('/movies/search')
def movies_search():
    """Search movies"""
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('movies_home'))
    
    # Search in cached movies
    results = []
    query_lower = query.lower()
    for m in cached_movies:
        if query_lower in m.get('title', '').lower():
            results.append(m)
    
    return render_template('movies/search.html', query=query, movies=results, total_results=len(results))

# ==================== STATIC ROUTES ====================

@app.route('/fetch-now', methods=['POST'])
def fetch_now():
    """Trigger immediate fetch"""
    # Trigger background fetch immediately
    Thread(target=background_fetch, daemon=True).start()
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
    print("🌐 GLOBE NEWS - RESILIENT VERSION")
    print("="*60)
    print(f"🔗 Backend: {BACKEND_URL}")
    print("📊 Mode: Background fetch with instant cache")
    print("="*60)
    
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=False,
        threaded=True
    )
