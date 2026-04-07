"""
Globe News Frontend - Complete Version
Connected to Backend v6.1 with Full Content Extraction & Human Summaries
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from functools import lru_cache
from datetime import datetime, timedelta
import requests
import html
import re
import os
import logging
import time

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Backend API configuration
BACKEND_URL = os.environ.get('BACKEND_URL', 'https://globenew--backend-api--5pt6gkpwq49b.code.run')
API_VERSION = "v1"

# Increased timeout values
DEFAULT_TIMEOUT = 30
LONG_TIMEOUT = 45

# Simple in-memory cache
cache = {}
CACHE_TTL = 300  # 5 minutes

def get_cached_or_fetch(cache_key, fetch_func, ttl=CACHE_TTL):
    """Get data from cache or fetch with timeout"""
    now = time.time()
    if cache_key in cache:
        data, timestamp = cache[cache_key]
        if now - timestamp < ttl:
            logger.info(f"Cache hit for {cache_key}")
            return data
    
    logger.info(f"Cache miss for {cache_key}, fetching...")
    try:
        data = fetch_func()
        cache[cache_key] = (data, now)
        return data
    except Exception as e:
        logger.error(f"Error fetching {cache_key}: {e}")
        # Return cached data even if expired, or empty dict
        if cache_key in cache:
            logger.info(f"Using expired cache for {cache_key}")
            return cache[cache_key][0]
        return None

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

@app.template_filter('format_date')
def format_date(value):
    if not value:
        return "Unknown date"
    try:
        if 'T' in value:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%b %d, %Y')
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
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "just now"
    except:
        return value

@app.template_filter('safe_html')
def safe_html(text):
    if not text:
        return ""
    text = re.sub(r'<script.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    return text

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

# ==================== API HELPER FUNCTIONS ====================

def fetch_articles(params=None):
    """Fetch articles from backend API with timeout and retry."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles"
        logger.info(f"Fetching articles from: {url}")
        
        response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        logger.info(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            articles = data.get('articles', [])
            total = data.get('total', 0)
            logger.info(f"Success: Got {len(articles)} articles, total={total}")
            return data
        else:
            logger.error(f"API returned status {response.status_code}")
            return {"articles": [], "total": 0}
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching articles after {DEFAULT_TIMEOUT}s")
        return {"articles": [], "total": 0}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching articles: {e}")
        return {"articles": [], "total": 0}

def fetch_article(article_id):
    """Fetch single article from backend API."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles/{article_id}"
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        if 'human_summary' not in data:
            data['human_summary'] = None
        if 'preview_content' not in data:
            data['preview_content'] = None
        if 'full_content' not in data:
            data['full_content'] = None
        if 'category_name' not in data:
            data['category_name'] = 'General'
            
        return data
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching article {article_id}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching article {article_id}: {e}")
        return None

def fetch_categories():
    """Fetch categories from backend API."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/categories"
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error("Timeout fetching categories")
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching categories: {e}")
        return []

def fetch_breaking_articles():
    """Fetch breaking news articles."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/articles/breaking/"
        response = requests.get(url, params={"limit": 10}, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error("Timeout fetching breaking articles")
        return {"articles": []}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching breaking articles: {e}")
        return {"articles": []}

def fetch_trending_movies(media_type='all', limit=20):
    """Fetch trending movies and TV shows from backend."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/trending"
        params = {'media_type': media_type, 'limit': limit}
        response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching trending movies")
        return {"movies": [], "count": 0}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching trending movies: {e}")
        return {"movies": [], "count": 0}

def fetch_movie_details(movie_id):
    """Fetch single movie details by TMDB ID."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/{movie_id}"
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching movie {movie_id}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching movie {movie_id}: {e}")
        return None

def search_movies(query):
    """Search for movies by title."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/movies/search"
        params = {'query': query}
        response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Timeout searching movies for: {query}")
        return {"results": [], "count": 0}
    except requests.exceptions.RequestException as e:
        logger.error(f"Error searching movies: {e}")
        return {"results": [], "count": 0}

def fetch_preview(article_id):
    """Fetch content preview for article."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}"
        response = requests.get(url, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching preview for article {article_id}: {e}")
        return None

def generate_preview(article_id):
    """Generate new preview for article."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/preview/articles/{article_id}/generate"
        response = requests.post(url, timeout=LONG_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error generating preview for article {article_id}: {e}")
        return None

def trigger_fetch():
    """Trigger manual news fetch."""
    try:
        url = f"{BACKEND_URL}/api/{API_VERSION}/fetcher/fetch-now"
        response = requests.post(url, timeout=LONG_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error triggering fetch: {e}")
        return {"message": "Error triggering fetch"}

# ==================== ROUTES ====================

@app.route('/')
def index():
    """Homepage - Latest news with 60 articles and trending movies"""
    language = request.args.get('language', 'all')
    page = request.args.get('page', 1, type=int)
    limit = 60
    skip = (page - 1) * limit
    
    # Fetch articles (with shorter timeout, don't block on failure)
    articles = []
    total_articles = 0
    total_pages = 1
    
    try:
        articles_data = fetch_articles({
            'limit': limit, 
            'skip': skip,
            'language': language
        })
        articles = articles_data.get('articles', [])
        total_articles = articles_data.get('total', 0)
        total_pages = (total_articles + limit - 1) // limit if total_articles > 0 else 1
    except Exception as e:
        logger.error(f"Failed to fetch articles for homepage: {e}")
    
    # Fetch breaking articles (non-blocking)
    breaking_articles = []
    try:
        breaking_data = fetch_breaking_articles()
        breaking_articles = breaking_data.get('articles', [])[:5]
    except Exception as e:
        logger.error(f"Failed to fetch breaking articles: {e}")
    
    # Fetch categories (non-blocking)
    categories = []
    try:
        categories = fetch_categories()
        for category in categories:
            try:
                cat_data = fetch_articles({'category': category['name'], 'limit': 1})
                category['article_count'] = cat_data.get('total', 0)
            except:
                category['article_count'] = 0
    except Exception as e:
        logger.error(f"Failed to fetch categories: {e}")
    
    # Fetch trending movies (non-blocking)
    trending_movies = []
    try:
        trending_movies_data = fetch_trending_movies('all', 6)
        trending_movies = trending_movies_data.get('movies', [])
    except Exception as e:
        logger.error(f"Failed to fetch trending movies: {e}")
    
    logger.info(f"RENDER: {len(articles)} articles, {len(breaking_articles)} breaking, {len(trending_movies)} movies")
    
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
    """Article detail page with human summary support."""
    try:
        article = fetch_article(article_id)
        
        if not article:
            logger.warning(f"Article {article_id} not found")
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
            content_warning = "⚠️ Limited content available - only RSS summary was fetched"
        
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
        logger.error(f"Error in article_detail for {article_id}: {e}")
        return render_template('error.html', 
                             message="An error occurred loading the article",
                             error_code=500), 500

@app.route('/article/<int:article_id>/regenerate-preview')
def regenerate_preview(article_id):
    """Regenerate preview for article."""
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
    """Categories listing page."""
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
    """Individual category page."""
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
    """Breaking news page."""
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
    """Search results page."""
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
    """Movies and TV Shows homepage."""
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
    """Movie detail page."""
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
    """Search movies page."""
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
    """Trigger manual news fetch."""
    result = trigger_fetch()
    return redirect(url_for('index'))

@app.route('/api/health')
def api_health():
    """API health check."""
    try:
        response = requests.get(f"{BACKEND_URL}/api/{API_VERSION}/health/status", timeout=10)
        backend_status = response.json() if response.status_code == 200 else {"status": "unreachable"}
        
        return jsonify({
            "frontend": "healthy",
            "backend": backend_status,
            "timestamp": datetime.now().isoformat()
        })
    except requests.exceptions.RequestException:
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
    return render_template('error.html', 
                          message="Page not found",
                          error_code=404), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', 
                          message="Internal server error",
                          error_code=500), 500

# ==================== SEO ROUTES ====================

@app.route('/sitemap.xml')
def sitemap():
    from flask import Response
    
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://globe-news-jade.vercel.app/</loc>
    <changefreq>hourly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://globe-news-jade.vercel.app/breaking</loc>
    <changefreq>hourly</changefreq>
    <priority>0.9</priority>
  </url>
  <url>
    <loc>https://globe-news-jade.vercel.app/categories</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://globe-news-jade.vercel.app/movies</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://globe-news-jade.vercel.app/search</loc>
    <changefreq>monthly</changefreq>
    <priority>0.5</priority>
  </url>
</urlset>'''
    
    return Response(xml, mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    from flask import Response
    
    robots_txt = f"""User-agent: *
Allow: /
Sitemap: https://globe-news-jade.vercel.app/sitemap.xml

Disallow: /fetch-now
"""
    return Response(robots_txt, mimetype='text/plain')

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🌐 GLOBE NEWS FRONTEND - Starting Server")
    print("="*60)
    print(f"📱 Frontend: http://localhost:5000")
    print(f"🔗 Backend: {BACKEND_URL}")
    print(f"📊 Version: 3.0.0 (with Movies & TV Shows)")
    print("="*60)
    
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=True
    )
