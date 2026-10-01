from flask import current_app
import os
import math
import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, jsonify, abort, Response, session
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import markdown2
from slugify import slugify
import base64
import uuid

# ==========================================
# 1. CONFIGURATION
# ==========================================
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-jerry-space-2026-change-in-prod')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///rolynsspace.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    DOMAIN = 'jerry.tunupublishers.com'
    SITE_NAME = 'Jerry Rolyns Space'

# ==========================================
# 2. MODELS & DATABASE
# ==========================================
db = SQLAlchemy()

article_tags = db.Table('article_tags',
    db.Column('article_id', db.Integer, db.ForeignKey('articles.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id'), primary_key=True)
)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    avatar_url = db.Column(db.String(256), nullable=True)
    articles = db.relationship('Article', backref='author', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    articles = db.relationship('Article', backref='category', lazy='dynamic')

class Tag(db.Model):
    __tablename__ = 'tags'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    slug = db.Column(db.String(32), unique=True, nullable=False)

class Article(db.Model):
    __tablename__ = 'articles'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    summary = db.Column(db.Text, nullable=False)
    content_markdown = db.Column(db.Text, nullable=False)
    content_html = db.Column(db.Text, nullable=False)
    featured_image = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='published') # 'draft' or 'published'
    is_featured = db.Column(db.Boolean, default=False)
    views_count = db.Column(db.Integer, default=0)
    reading_time = db.Column(db.Integer, default=1)
    published_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    
    tags = db.relationship('Tag', secondary=article_tags, backref=db.backref('articles', lazy='dynamic'))
    comments = db.relationship('Comment', backref='article', lazy='dynamic', cascade='all, delete-orphan')

    def compute_reading_time(self):
        words = len(self.content_markdown.split())
        self.reading_time = max(1, math.ceil(words / 200))

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False)
    author_name = db.Column(db.String(100), nullable=False)
    author_email = db.Column(db.String(120), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_approved = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Subscriber(db.Model):
    __tablename__ = 'subscribers'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    
class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


# ==========================================
# 3. ADMIN BLUEPRINT & AUTH LOGIC
# ==========================================
from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access the admin area.', 'error')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function


def upload_image(filename):
    if not filename:
        return None
    upload_path = os.path.join(Config.UPLOAD_FOLDER, filename)
    return f"/static/uploads/{filename}"

@admin_bp.route('/upload_image',methods=['POST'])
@login_required
def upload_image():
    data=request.get_json()
    image=data.get('base64Image')
    if not image:return jsonify({'error':'No base64 image provided'}),400
    try:
        filename=f"{uuid.uuid4()}.png"
        with open(os.path.join(Config.UPLOAD_FOLDER,filename),'wb') as f:f.write(base64.b64decode(image.split(',',1)[-1]))
        return jsonify({'success':True,'url':f"/static/uploads/{filename}"})
    except Exception as e:
        return jsonify({'error':str(e)}),500
@admin_bp.route('/login',methods=['GET','POST'])
def login():
    if session.get('user_id') and session.get('username'):
        return redirect(url_for('admin.dashboard'))

    if request.method=='POST':
        username=request.form.get('username')
        password=request.form.get('password')
        user=User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id']=user.id
            session['username']=user.username
            flash('Logged in successfully.','success')
            return redirect(url_for('admin.dashboard'))

        flash('Invalid username or password.','error')

    return render_template('admin/login.html')

@admin_bp.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@admin_bp.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500


@admin_bp.route('/messages')
@login_required
def messages():
    messages = Message.query.order_by(Message.created_at.desc()).all()
    return render_template('admin/messages.html', messages=messages)

@admin_bp.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

@admin_bp.route('/')
@login_required
def dashboard():
    total_articles = Article.query.count()
    total_comments = Comment.query.count()
    total_subscribers = Subscriber.query.count()
    total_messages = Message.query.count()
    articles = Article.query.order_by(Article.created_at.desc()).all()
    comments = Comment.query.order_by(Comment.created_at.desc()).limit(10).all()
    categories = Category.query.all()
    return render_template('admin/dashboard.html',
                           total_articles=total_articles,
                           total_comments=total_comments,
                           total_subscribers=total_subscribers,
                           total_messages=total_messages,
                           articles=articles,
                           comments=comments,
                           categories=categories)

@admin_bp.route('/articles/new', methods=['GET', 'POST'])
@login_required
def article_create():
    categories = Category.query.all()
    if request.method == 'POST':
        title = request.form.get('title')
        summary = request.form.get('summary')
        content_markdown = request.form.get('content_markdown')
        category_id = request.form.get('category_id')
        status = request.form.get('status', 'published')
        is_featured = True if request.form.get('is_featured') else False
        
        slug = slugify(title)
        # Handle duplicate slugs
        base_slug = slug
        counter = 1
        while Article.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        content_html = markdown2.markdown(content_markdown, extras=['fenced-code-blocks', 'tables'])
        
        # Featured image upload handling
        featured_image = None
        file = request.files.get('featured_image')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(upload_path)
            featured_image = f"/static/uploads/{filename}"

        article = Article(
            title=title,
            slug=slug,
            summary=summary,
            content_markdown=content_markdown,
            content_html=content_html,
            category_id=category_id,
            author_id=session['user_id'],
            status=status,
            is_featured=is_featured,
            featured_image=featured_image
        )
        article.compute_reading_time()
        
        db.session.add(article)
        db.session.commit()
        flash('Article created successfully!', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/editor.html', article=None, categories=categories)

@admin_bp.route('/articles/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def article_edit(id):
    article = Article.query.get_or_404(id)
    categories = Category.query.all()
    
    if request.method == 'POST':
        article.title = request.form.get('title')
        article.summary = request.form.get('summary')
        article.content_markdown = request.form.get('content_markdown')
        article.content_html = markdown2.markdown(article.content_markdown, extras=['fenced-code-blocks', 'tables'])
        article.category_id = request.form.get('category_id')
        article.status = request.form.get('status', 'published')
        article.is_featured = True if request.form.get('is_featured') else False
        
        file = request.files.get('featured_image')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(upload_path)
            article.featured_image = f"/static/uploads/{filename}"
            
        article.compute_reading_time()
        db.session.commit()
        flash('Article updated successfully!', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/editor.html', article=article, categories=categories)

@admin_bp.route('/articles/<int:id>/delete', methods=['POST'])
@login_required
def article_delete(id):
    article = Article.query.get_or_404(id)
    db.session.delete(article)
    db.session.commit()
    flash('Article deleted.', 'success')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/comments/<int:id>/delete', methods=['POST'])
@login_required
def comment_delete(id):
    comment = Comment.query.get_or_404(id)
    db.session.delete(comment)
    db.session.commit()
    flash('Comment deleted.', 'success')
    return redirect(url_for('admin.dashboard'))


# ==========================================
# 4. APPLICATION FACTORY & MAIN ROUTES
# ==========================================
from flask import current_app

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    db.init_app(app)
    app.register_blueprint(admin_bp)
    
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

    @app.context_processor
    def inject_global_vars():
        categories = Category.query.all()
        return dict(
            site_name=app.config['SITE_NAME'],
            domain=app.config['DOMAIN'],
            global_categories=categories
        )
        
        
    from flask import make_response, send_from_directory
    from pathlib import Path

    @app.get("/service-worker.js")
    def service_worker():
        response = make_response(
            send_from_directory(Path(app.static_folder), "service-worker.js")
        )
        response.headers["Service-Worker-Allowed"] = "/"
        response.headers["Content-Type"] = "application/javascript; charset=utf-8"
        response.headers["Cache-Control"] = "no-cache"
        return response


    @app.route('/')
    def index():
        featured_articles = Article.query.filter_by(status='published', is_featured=True)\
            .order_by(Article.published_at.desc()).limit(3).all()
            
        latest_articles = Article.query.filter_by(status='published')\
            .order_by(Article.published_at.desc()).limit(6).all()
            
        popular_articles = Article.query.filter_by(status='published')\
            .order_by(Article.views_count.desc()).limit(4).all()

        return render_template('index.html',
                               featured_articles=featured_articles,
                               latest_articles=latest_articles,
                               popular_articles=popular_articles)

    @app.route('/articles')
    def articles_list():
        page = request.args.get('page', 1, type=int)
        category_slug = request.args.get('category', type=str)
        tag_slug = request.args.get('tag', type=str)
        
        query = Article.query.filter_by(status='published')
        
        selected_category = None
        if category_slug:
            selected_category = Category.query.filter_by(slug=category_slug).first_or_404()
            query = query.filter_by(category_id=selected_category.id)
            
        selected_tag = None
        if tag_slug:
            selected_tag = Tag.query.filter_by(slug=tag_slug).first_or_404()
            query = query.filter(Article.tags.contains(selected_tag))
            
        pagination = query.order_by(Article.published_at.desc()).paginate(page=page, per_page=9)
        
        return render_template('articles.html',
                               articles=pagination.items,
                               pagination=pagination,
                               selected_category=selected_category,
                               selected_tag=selected_tag)

    @app.route('/articles/<slug>')
    def article_detail(slug):
        article = Article.query.filter_by(slug=slug, status='published').first_or_404()
        
        article.views_count += 1
        db.session.commit()
        
        related_articles = Article.query.filter(
            Article.category_id == article.category_id,
            Article.id != article.id,
            Article.status == 'published'
        ).order_by(Article.published_at.desc()).limit(3).all()
        
        prev_article = Article.query.filter(
            Article.published_at < article.published_at,
            Article.status == 'published'
        ).order_by(Article.published_at.desc()).first()
        
        next_article = Article.query.filter(
            Article.published_at > article.published_at,
            Article.status == 'published'
        ).order_by(Article.published_at.asc()).first()
        
        comments = article.comments.filter_by(is_approved=True).order_by(Comment.created_at.desc()).all()

        return render_template('article_detail.html',
                               article=article,
                               related_articles=related_articles,
                               prev_article=prev_article,
                               next_article=next_article,
                               comments=comments)

    @app.route('/articles/<slug>/comment', methods=['POST'])
    def add_comment(slug):
        article = Article.query.filter_by(slug=slug, status='published').first_or_404()
        name = request.form.get('author_name', '').strip()
        email = request.form.get('author_email', '').strip()
        content = request.form.get('content', '').strip()

        if name and email and content:
            comment = Comment(
                article_id=article.id,
                author_name=name,
                author_email=email,
                content=content,
                is_approved=True
            )
            db.session.add(comment)
            db.session.commit()
            flash('Thank you for your comment!', 'success')
        else:
            flash('Please complete all fields.', 'error')

        return redirect(url_for('article_detail', slug=slug))

    @app.route('/categories')
    def categories_list():
        categories = Category.query.all()
        return render_template('categories.html', categories=categories)

    @app.route('/search')
    def search():
        q = request.args.get('q', '').strip()
        results = []
        if q:
            search_pattern = f"%{q}%"
            results = Article.query.filter(
                Article.status == 'published',
                (Article.title.ilike(search_pattern)) | 
                (Article.summary.ilike(search_pattern)) | 
                (Article.content_markdown.ilike(search_pattern))
            ).order_by(Article.published_at.desc()).all()
            
        return render_template('search.html', query=q, results=results)

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/contact', methods=['GET', 'POST'])
    def contact():
        if request.method == 'POST':
            name = request.form.get('name')
            email = request.form.get('email')
            message = request.form.get('message')
            message = Message(name=name, email=email, message=message)
            db.session.add(message)
            db.session.commit()
            flash('Message received! Jerry will get back to you soon.', 'success')
            return redirect(url_for('contact'))
        return render_template('contact.html')

    @app.route('/subscribe', methods=['POST'])
    def subscribe():
        email = request.form.get('email', '').strip()
        if email:
            existing = Subscriber.query.filter_by(email=email).first()
            if not existing:
                sub = Subscriber(email=email)
                db.session.add(sub)
                db.session.commit()
                flash('Subscribed successfully!', 'success')
            else:
                flash('You are already subscribed.', 'info')
        return redirect(request.referrer or url_for('index'))

    @app.route('/rss.xml')
    def rss_feed():
        articles = Article.query.filter_by(status='published').order_by(Article.published_at.desc()).limit(20).all()
        xml = render_template('rss.xml', articles=articles)
        return Response(xml, mimetype='application/rss+xml')

    @app.route('/sitemap.xml')
    def sitemap():
        articles = Article.query.filter_by(status='published').all()
        categories = Category.query.all()
        xml = render_template('sitemap.xml', articles=articles, categories=categories)
        return Response(xml, mimetype='application/xml')

    @app.route('/robots.txt')
    def robots():
        content = "User-agent: *\nAllow: /\nSitemap: https://jerry.tunupublishers.com/sitemap.xml"
        return Response(content, mimetype='text/plain')

    return app


def init_db(app):
    with app.app_context():
        db.create_all()
        if db.session.query(Category).count() == 0:
            default_categories = [
                ('Technology', 'Insights into systems, tech ecosystems and hardware.'),
                ('Life', 'Reflections on experiences, balance and human connections.'),
                ('Ideas', 'Abstract concepts, future predictions and thought experiments.'),
                ('Stories', 'Narratives, personal anecdotes and creative journeys.'),
                ('Tutorials', 'Step-by-step walkthroughs to build real life projects.'),
                ('Productivity', 'Systems, tools and habits for focused execution.'),
                ('Health', 'Physical, mental and emotional well-being.'),
                ('Finance', 'Personal finance, investing and economic insights.'),
                ('Digital World', 'Analysis of digital culture, open source and privacy.'),
                ('Science', 'Research, discoveries and scientific advancements.'),
                ('Art', 'Creative expression, design and visual arts.'),
                ('Music', 'Reviews, recommendations and musical analysis.'),
                ('Books', 'Reviews, recommendations and literary analysis.'),
                ('Movies', 'Reviews, recommendations and film analysis.'),
                ('TV', 'Reviews, recommendations and TV show analysis.'),
                ('Food', 'Reviews, recommendations and food analysis.'),
                ('Politics', 'Analysis of political systems, policies and global affairs.'),
                ('History', 'Analysis of historical events, trends and cultural heritage.'),
                ('Philosophy', 'Analysis of philosophical concepts, theories and ideas.'),
                ('Religion', 'Analysis of religious beliefs, practices and spiritual experiences.'),
                ('Social Sciences', 'Analysis of social structures, human behavior and societal dynamics.'),
                ('Environment', 'Analysis of environmental issues, sustainability and conservation efforts.'),
                ('Travel', 'Analysis of travel destinations, experiences and cultural insights.'),
                ('Fashion', 'Analysis of fashion trends, styles and cultural influences.'),
                ('Gaming', 'Reviews, recommendations and gaming analysis.'),
                ('Sports', 'Reviews, recommendations and sports analysis.'),
                ('Soccer', 'Reviews, recommendations and soccer analysis.'),
                ('Story Telling', 'Reviews, recommendations and story telling analysis.'),
                ('Investing', 'Reviews, recommendations and investing analysis.'),
                ('Media', 'Reviews, recommendations and media analysis.'),
            ]
            for name, desc in default_categories:
                cat = Category(name=name, slug=slugify(name), description=desc)
                db.session.add(cat)
            db.session.commit()
            
        if not User.query.first():
            admin_user = User(
                username='jerry',
                email='jerry@tunupublishers.com',
                bio='Writer, editor and creator of Jerry Rolyns Space.'
            )
            admin_user.set_password('jerryspace2026')
            db.session.add(admin_user)
            db.session.commit()

app = create_app()

if __name__ == '__main__':
    init_db(app)
    app.run(debug=True, host='0.0.0.0', port=5000)