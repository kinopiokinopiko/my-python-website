from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import yfinance as yf
import requests
import re
from bs4 import BeautifulSoup
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # セッション用の秘密鍵

# Flask-Loginのセットアップ
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# サンプルユーザー（A, B, C）
USERS = {
    'A': {'password': 'a123'},
    'B': {'password': 'b123'},
    'C': {'password': 'c123'},
}

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(user_id):
    if user_id in USERS:
        return User(user_id)
    return None

def get_data_file():
    if current_user.is_authenticated:
        return f'asset_data_{current_user.id}.json'
    return 'asset_data_guest.json'

def load_data():
    """ユーザーごとのデータファイルから資産情報を読み込み"""
    data_file = get_data_file()
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {
        'jp_stocks': [],
        'us_stocks': [],
        'funds': [],
        'crypto': [],
        'gold_qty': 0,
        'cash_jpy': 0,
        'last_updated': None
    }

def save_data(data):
    """ユーザーごとのデータファイルに保存"""
    data['last_updated'] = datetime.now().isoformat()
    data_file = get_data_file()
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_jp_stock_info(code):
    """日本株の情報を取得"""
    try:
        ticker = yf.Ticker(f"{code}.T")
        info = ticker.info
        current_price = info.get('currentPrice', 0)
        if current_price == 0:
            hist = ticker.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
        
        return {
            'name': info.get('longName', f'Stock {code}'),
            'price': round(current_price, 2) if current_price else 0
        }
    except:
        return {'name': f'Stock {code}', 'price': 0}

def get_us_stock_info(symbol):
    """米国株の情報を取得"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        current_price = info.get('currentPrice', 0)
        if current_price == 0:
            hist = ticker.history(period="1d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
        
        return {
            'name': info.get('longName', symbol),
            'price': round(current_price, 2) if current_price else 0
        }
    except:
        return {'name': symbol, 'price': 0}

def get_usd_jpy_rate():
    """USD→円レートを取得"""
    try:
        # yfinanceを使用してUSD/JPYレートを取得
        ticker = yf.Ticker('USDJPY=X')
        hist = ticker.history(period="1d")
        if not hist.empty:
            return round(hist['Close'].iloc[-1], 2)
        
        # バックアップ: Yahoo Financeからスクレイピング
        fx_res = requests.get('https://finance.yahoo.com/quote/USDJPY=X/', 
                             headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, 
                             timeout=10)
        fx_html = fx_res.text
        fx_match = re.search(r'"regularMarketPrice":\{"raw":([0-9.]+)', fx_html)
        if fx_match:
            return round(float(fx_match.group(1)), 2)
        
        # さらなるバックアップ
        fx_match = re.search(r'"regularMarketPrice":([0-9.]+)', fx_html)
        if fx_match:
            return round(float(fx_match.group(1)), 2)
        
        return 150.0  # デフォルトレート
    except Exception as e:
        print(f"USD/JPY rate fetch error: {e}")
        return 150.0  # デフォルトレート

def get_gold_price():
    """金価格を取得"""
    try:
        tanaka_url = "https://gold.tanaka.co.jp/commodity/souba/english/index.php"
        res = requests.get(tanaka_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) > 1 and tds[0].get_text(strip=True).upper() == "GOLD":
                price_text = tds[1].get_text(strip=True)
                price_match = re.search(r"([0-9,]+) yen", price_text)
                if price_match:
                    return int(price_match.group(1).replace(",", ""))
        return 0  # 取得できなかった場合は0を返す
    except:
        return 0

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and USERS[username]['password'] == password:
            user = User(username)
            login_user(user)
            return redirect(url_for('dashboard'))
        return 'ログイン失敗'
    return '''
    <form method="post">
        <input name="username" placeholder="ユーザー名(A/B/C)">
        <input name="password" type="password" placeholder="パスワード(a123/b123/c123)">
        <button type="submit">ログイン</button>
    </form>
    '''

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    """メインダッシュボード"""
    data = load_data()
    
    # 各資産の評価額を計算
    jp_total = sum(stock['qty'] * stock['price'] for stock in data['jp_stocks'])
    
    # USD→円レート取得
    usd_jpy = get_usd_jpy_rate()
    us_total_usd = sum(stock['qty'] * stock['price'] for stock in data['us_stocks'])
    us_total_jpy = int(us_total_usd * usd_jpy) if usd_jpy else 0
    
    fund_total = sum(fund['qty'] * fund['price'] for fund in data['funds'])
    crypto_total = 0  # 仮想通貨は後で実装
    gold_price = get_gold_price()
    gold_total = (data.get('gold_qty') or 0) * gold_price
    
    template = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>資産情報ダッシュボード</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .asset-link { color: #0066cc; text-decoration: none; }
            .asset-link:hover { text-decoration: underline; }
            .nav-links { margin: 20px 0; }
            .nav-links a { margin-right: 15px; padding: 5px 10px; background: #0066cc; color: white; text-decoration: none; border-radius: 3px; }
            .nav-links a:hover { background: #0052a3; }
            .total { font-weight: bold; background-color: #e8f4fd; }
            .rate-info { margin: 10px 0; font-size: 14px; color: #666; }
        </style>
    </head>
    <body>
        <h1>資産情報ダッシュボード</h1>
        
        <div class="rate-info">
            USD/JPY レート: {{ "{:,.2f}".format(usd_jpy) }} 円
        </div>
        
        <div class="nav-links">
            <a href="{{ url_for('jp_stocks') }}">日本株管理</a>
            <a href="{{ url_for('us_stocks') }}">米国株管理</a>
            <a href="{{ url_for('funds') }}">投資信託管理</a>
            <a href="{{ url_for('gold') }}">金管理</a>
            <a href="{{ url_for('cash') }}">現金管理</a>
        </div>
        
        <table>
            <tr>
                <th>資産</th>
                <th>評価額</th>
            </tr>
            <tr>
                <td><a href="{{ url_for('jp_stocks') }}" class="asset-link">日本株</a></td>
                <td>{{ "{:,}".format(jp_total|int) }} 円</td>
            </tr>
            <tr>
                <td><a href="{{ url_for('us_stocks') }}" class="asset-link">米国株</a></td>
                <td>{{ "{:,}".format(us_total_jpy|int) }} 円（${{ "{:,.2f}".format(us_total_usd) }}）</td>
            </tr>
            <tr>
                <td><a href="{{ url_for('funds') }}" class="asset-link">投資信託</a></td>
                <td>{{ "{:,}".format(fund_total|int) }} 円</td>
            </tr>
            <tr>
                <td>仮想通貨</td>
                <td>0 USD</td>
            </tr>
            <tr>
                <td><a href="{{ url_for('gold') }}" class="asset-link">金 (Gold)</a></td>
                <td>{{ "{:,}".format(gold_total|int) }} 円</td>
            </tr>
            <tr>
                <td><a href="{{ url_for('cash') }}" class="asset-link">現金</a></td>
                <td>{{ "{:,}".format(data.cash_jpy|int) }} 円</td>
            </tr>
            <tr class="total">
                <td>合計</td>
                <td>{{ "{:,}".format((jp_total + fund_total + gold_total + data.cash_jpy + us_total_jpy)|int) }} 円</td>
            </tr>
        </table>
        
        {% if data.last_updated %}
        <p><small>最終更新: {{ data.last_updated[:19] }}</small></p>
        {% endif %}
    </body>
    </html>
    """
    
    return render_template_string(template, jp_total=jp_total, us_total_usd=us_total_usd, us_total_jpy=us_total_jpy, fund_total=fund_total, gold_total=gold_total, data=data, usd_jpy=usd_jpy)

@app.route('/jp_stocks')
def jp_stocks():
    """日本株管理ページ"""
    data = load_data()
    
    template = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>日本株ダッシュボード</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .form-group { margin: 10px 0; }
            input[type="text"], input[type="number"] { padding: 5px; margin: 5px; }
            button { padding: 8px 15px; background: #0066cc; color: white; border: none; border-radius: 3px; cursor: pointer; }
            button:hover { background: #0052a3; }
            .back-link { margin: 20px 0; }
            .back-link a { color: #0066cc; text-decoration: none; }
            .delete-btn { background: #dc3545; padding: 4px 8px; font-size: 12px; }
            .delete-btn:hover { background: #c82333; }
        </style>
    </head>
    <body>
        <div class="back-link"><a href="{{ url_for('dashboard') }}">← ダッシュボードに戻る</a></div>
        
        <h1>日本株ダッシュボード</h1>
        
        <form method="POST" action="{{ url_for('add_jp_stock') }}">
            <div class="form-group">
                <input type="text" name="code" placeholder="証券コード" required>
                <input type="number" name="qty" step="1" placeholder="数量" required>
                <button type="submit">追加</button>
            </div>
        </form>
        
        <table>
            <tr>
                <th>会社名</th>
                <th>証券コード</th>
                <th>数量</th>
                <th>株価</th>
                <th>評価額</th>
                <th>操作</th>
            </tr>
            {% for stock in data.jp_stocks %}
            <tr>
                <td>{{ stock.name }}</td>
                <td>{{ stock.code }}</td>
                <td>{{ stock.qty }}</td>
                <td>{{ "{:,.2f}".format(stock.price) }} 円</td>
                <td>{{ "{:,}".format((stock.qty * stock.price)|int) }} 円</td>
                <td>
                    <form method="POST" action="{{ url_for('delete_jp_stock') }}" style="display: inline;">
                        <input type="hidden" name="code" value="{{ stock.code }}">
                        <button type="submit" class="delete-btn" onclick="return confirm('削除しますか？')">削除</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    
    return render_template_string(template, data=data)

@app.route('/add_jp_stock', methods=['POST'])
def add_jp_stock():
    """日本株を追加"""
    data = load_data()
    code = request.form['code']
    qty = int(request.form['qty'])
    
    stock_info = get_jp_stock_info(code)
    
    # 既存の株式を更新するか新規追加
    for stock in data['jp_stocks']:
        if stock['code'] == code:
            stock['qty'] = qty
            stock['price'] = stock_info['price']
            stock['name'] = stock_info['name']
            break
    else:
        data['jp_stocks'].append({
            'code': code,
            'name': stock_info['name'],
            'qty': qty,
            'price': stock_info['price']
        })
    
    save_data(data)
    return redirect(url_for('jp_stocks'))

@app.route('/delete_jp_stock', methods=['POST'])
def delete_jp_stock():
    """日本株を削除"""
    data = load_data()
    code = request.form['code']
    data['jp_stocks'] = [stock for stock in data['jp_stocks'] if stock['code'] != code]
    save_data(data)
    return redirect(url_for('jp_stocks'))

@app.route('/us_stocks')
def us_stocks():
    """米国株管理ページ"""
    data = load_data()
    usd_jpy = get_usd_jpy_rate()
    
    template = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>米国株ダッシュボード</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .form-group { margin: 10px 0; }
            input[type="text"], input[type="number"] { padding: 5px; margin: 5px; }
            button { padding: 8px 15px; background: #0066cc; color: white; border: none; border-radius: 3px; cursor: pointer; }
            button:hover { background: #0052a3; }
            .back-link { margin: 20px 0; }
            .back-link a { color: #0066cc; text-decoration: none; }
            .delete-btn { background: #dc3545; padding: 4px 8px; font-size: 12px; }
            .delete-btn:hover { background: #c82333; }
            .rate-info { margin: 10px 0; font-size: 14px; color: #666; }
        </style>
    </head>
    <body>
        <div class="back-link"><a href="{{ url_for('dashboard') }}">← ダッシュボードに戻る</a></div>
        
        <h1>米国株ダッシュボード</h1>
        
        <div class="rate-info">
            USD/JPY レート: {{ "{:,.2f}".format(usd_jpy) }} 円
        </div>
        
        <form method="POST" action="{{ url_for('add_us_stock') }}">
            <div class="form-group">
                <input type="text" name="symbol" placeholder="ティッカーシンボル" required>
                <input type="number" name="qty" step="0.01" placeholder="数量" required>
                <button type="submit">追加</button>
            </div>
        </form>
        
        <table>
            <tr>
                <th>会社名</th>
                <th>シンボル</th>
                <th>数量</th>
                <th>株価(USD)</th>
                <th>株価(JPY)</th>
                <th>評価額(USD)</th>
                <th>評価額(JPY)</th>
                <th>操作</th>
            </tr>
            {% for stock in data.us_stocks %}
            <tr>
                <td>{{ stock.name }}</td>
                <td>{{ stock.symbol }}</td>
                <td>{{ stock.qty }}</td>
                <td>${{ "{:,.2f}".format(stock.price) }}</td>
                <td>{{ "{:,.0f}".format(stock.price * usd_jpy) }} 円</td>
                <td>${{ "{:,.2f}".format(stock.qty * stock.price) }}</td>
                <td>{{ "{:,}".format((stock.qty * stock.price * usd_jpy)|int) }} 円</td>
                <td>
                    <form method="POST" action="{{ url_for('delete_us_stock') }}" style="display: inline;">
                        <input type="hidden" name="symbol" value="{{ stock.symbol }}">
                        <button type="submit" class="delete-btn" onclick="return confirm('削除しますか？')">削除</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    
    return render_template_string(template, data=data, usd_jpy=usd_jpy)

@app.route('/add_us_stock', methods=['POST'])
def add_us_stock():
    """米国株を追加"""
    data = load_data()
    symbol = request.form['symbol'].upper()
    qty = float(request.form['qty'])
    
    stock_info = get_us_stock_info(symbol)
    
    # 既存の株式を更新するか新規追加
    for stock in data['us_stocks']:
        if stock['symbol'] == symbol:
            stock['qty'] = qty
            stock['price'] = stock_info['price']
            stock['name'] = stock_info['name']
            break
    else:
        data['us_stocks'].append({
            'symbol': symbol,
            'name': stock_info['name'],
            'qty': qty,
            'price': stock_info['price']
        })
    
    save_data(data)
    return redirect(url_for('us_stocks'))

@app.route('/delete_us_stock', methods=['POST'])
def delete_us_stock():
    """米国株を削除"""
    data = load_data()
    symbol = request.form['symbol']
    data['us_stocks'] = [stock for stock in data['us_stocks'] if stock['symbol'] != symbol]
    save_data(data)
    return redirect(url_for('us_stocks'))

@app.route('/funds')
def funds():
    """投資信託管理ページ"""
    data = load_data()
    
    template = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>投資信託ダッシュボード</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .form-group { margin: 10px 0; }
            input[type="text"], input[type="number"] { padding: 5px; margin: 5px; }
            button { padding: 8px 15px; background: #0066cc; color: white; border: none; border-radius: 3px; cursor: pointer; }
            button:hover { background: #0052a3; }
            .back-link { margin: 20px 0; }
            .back-link a { color: #0066cc; text-decoration: none; }
            .delete-btn { background: #dc3545; padding: 4px 8px; font-size: 12px; }
            .delete-btn:hover { background: #c82333; }
        </style>
    </head>
    <body>
        <div class="back-link"><a href="{{ url_for('dashboard') }}">← ダッシュボードに戻る</a></div>
        
        <h1>投資信託ダッシュボード</h1>
        
        <form method="POST" action="{{ url_for('add_fund') }}">
            <div class="form-group">
                <input type="text" name="name" placeholder="ファンド名" required>
                <input type="number" name="qty" step="0.01" placeholder="口数" required>
                <input type="number" name="price" step="0.01" placeholder="基準価額" required>
                <button type="submit">追加</button>
            </div>
        </form>
        
        <table>
            <tr>
                <th>ファンド名</th>
                <th>口数</th>
                <th>基準価額</th>
                <th>評価額</th>
                <th>操作</th>
            </tr>
            {% for fund in data.funds %}
            <tr>
                <td>{{ fund.name }}</td>
                <td>{{ "{:,.2f}".format(fund.qty) }}</td>
                <td>{{ "{:,.2f}".format(fund.price) }} 円</td>
                <td>{{ "{:,}".format((fund.qty * fund.price)|int) }} 円</td>
                <td>
                    <form method="POST" action="{{ url_for('delete_fund') }}" style="display: inline;">
                        <input type="hidden" name="name" value="{{ fund.name }}">
                        <button type="submit" class="delete-btn" onclick="return confirm('削除しますか？')">削除</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    
    return render_template_string(template, data=data)

@app.route('/add_fund', methods=['POST'])
def add_fund():
    """投資信託を追加"""
    data = load_data()
    name = request.form['name']
    qty = float(request.form['qty'])
    price = float(request.form['price'])
    
    # 既存のファンドを更新するか新規追加
    for fund in data['funds']:
        if fund['name'] == name:
            fund['qty'] = qty
            fund['price'] = price
            break
    else:
        data['funds'].append({
            'name': name,
            'qty': qty,
            'price': price
        })
    
    save_data(data)
    return redirect(url_for('funds'))

@app.route('/delete_fund', methods=['POST'])
def delete_fund():
    """投資信託を削除"""
    data = load_data()
    name = request.form['name']
    data['funds'] = [fund for fund in data['funds'] if fund['name'] != name]
    save_data(data)
    return redirect(url_for('funds'))

@app.route('/gold')
def gold():
    """金管理ページ"""
    data = load_data()
    gold_price = get_gold_price()
    gold_total = data['gold_qty'] * gold_price
    
    template = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>金ダッシュボード</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
            th { background-color: #f2f2f2; }
            .form-group { margin: 10px 0; }
            input[type="number"] { padding: 5px; margin: 5px; }
            button { padding: 8px 15px; background: #0066cc; color: white; border: none; border-radius: 3px; cursor: pointer; }
            button:hover { background: #0052a3; }
            .back-link { margin: 20px 0; }
            .back-link a { color: #0066cc; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="back-link"><a href="{{ url_for('dashboard') }}">← ダッシュボードに戻る</a></div>
        
        <h1>金ダッシュボード</h1>
        
        <form method="POST" action="{{ url_for('update_gold') }}">
            <div class="form-group">
                <input type="number" name="qty" step="0.1" placeholder="数量(g)" value="{{ data.gold_qty }}" required>
                <button type="submit">更新</button>
            </div>
        </form>
        
        <table>
            <tr>
                <th>資産</th>
                <th>数量</th>
                <th>価格</th>
                <th>評価額</th>
            </tr>
            <tr>
                <td>金 (Gold)</td>
                <td>{{ data.gold_qty }} g</td>
                <td>{{ "{:,}".format(gold_price) }} 円/g</td>
                <td>{{ "{:,}".format(gold_total|int) }} 円</td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    return render_template_string(template, data=data, gold_price=gold_price, gold_total=gold_total)

@app.route('/update_gold', methods=['POST'])
def update_gold():
    """金の数量を更新"""
    data = load_data()
    data['gold_qty'] = float(request.form['qty'])
    save_data(data)
    return redirect(url_for('gold'))

@app.route('/cash')
def cash():
    """現金管理ページ"""
    data = load_data()
    
    template = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <title>現金管理</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .form-group { margin: 10px 0; }
            input[type="number"] { padding: 5px; margin: 5px; }
            button { padding: 8px 15px; background: #0066cc; color: white; border: none; border-radius: 3px; cursor: pointer; }
            button:hover { background: #0052a3; }
            .back-link { margin: 20px 0; }
            .back-link a { color: #0066cc; text-decoration: none; }
            .current-amount { font-size: 24px; color: #0066cc; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="back-link"><a href="{{ url_for('dashboard') }}">← ダッシュボードに戻る</a></div>
        
        <h1>現金管理</h1>
        
        <div class="current-amount">
            現在の現金: {{ "{:,}".format(data.cash_jpy|int) }} 円
        </div>
        
        <form method="POST" action="{{ url_for('update_cash') }}">
            <div class="form-group">
                <input type="number" name="amount" step="1" placeholder="金額(円)" value="{{ data.cash_jpy|int }}" required>
                <button type="submit">更新</button>
            </div>
        </form>
    </body>
    </html>
    """
    
    return render_template_string(template, data=data)

@app.route('/update_cash', methods=['POST'])
def update_cash():
    """現金額を更新"""
    data = load_data()
    data['cash_jpy'] = float(request.form['amount'])
    save_data(data)
    return redirect(url_for('cash'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)