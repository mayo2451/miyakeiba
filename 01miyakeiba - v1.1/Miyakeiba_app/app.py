from flask import Flask,render_template,request,redirect, session, url_for, flash # type: ignore
from flask_login import LoginManager, login_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
import calendar
from calendar import monthrange
import jpholiday # type: ignore
import sqlite3
import os
import gspread # type: ignore
from oauth2client.service_account import ServiceAccountCredentials # type: ignore
import time
import json
import hashlib
import threading
from datetime import datetime, date, timedelta

app = Flask(__name__)

SHEET_NAME = "miyakeiba_backup"
TABLES = ['race_entries', 'race_result', 'race_schedule', 'raise_horse', 'sqlite_sequence', 'users', 'timestamp']
BACKUP_INTERVAL = 600
DB_NAME = "miyakeiba_app.db"
SKIP_STARTUP_BACKUP = os.getenv("SKIP_STARTUP_BACKUP", "false").lower() == "true"
app.secret_key = 'your_secret_key'
JAPANESE_WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

login_manager = LoginManager()
login_manager.init_app(app)

def get_sheet_client():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)

def load_backup_from_sheet():
    print("📥 スプレッドシートからバックアップを読み込み中...")
    sheet = get_sheet_client()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for table in TABLES:
        try:
            print(f"📄 テーブル `{table}` を読み込み中...")
            worksheet = sheet.worksheet(table)
            data = worksheet.get_all_values()

            if not data or len(data) < 2:
                print(f"⚠️ `{table}` にデータがありません。スキップします。")
                continue

            columns = data[0]
            rows = data[1:]

            placeholders = ', '.join(['?'] * len(columns))
            columns_joined = ', '.join(columns)

            cursor.execute(f"DELETE FROM {table}")
            cursor.executemany(
                f"INSERT INTO {table} ({columns_joined}) VALUES ({placeholders})", rows
            )
            print(f"✅ `{table}` 読み込み完了")
        except Exception as e:
            print(f"❌ エラー（{table}）: {e}")
            continue

    conn.commit()
    conn.close()
    print("✅ 全テーブルの読み込み完了")
    
load_backup_from_sheet()

def get_last_backup_time():
    try:
        sheet = get_sheet_client()
        worksheet = sheet.worksheet("timestamp")
        value = worksheet.acell('A1').value
        return float(value) if value else 0.0
    except Exception as e:
        print(f"⚠️ タイムスタンプ取得エラー: {e}")
        return 0.0
        
def update_backup_time():
    try:
        sheet = get_sheet_client()
        worksheet = sheet.worksheet("timestamp")
        now = str(time.time())
        worksheet.update_acell('A1', now)
    except Exception as e:
        print(f"⚠️ タイムスタンプ更新エラー: {e}")
            
def run_backup_async():
    thread = threading.Thread(target=backup_all_tables)
    thread.start()
    
def startup_backup_check():
    if SKIP_STARTUP_BACKUP:
        print("🚫 起動時のバックアップはスキップされました。")
        return
    if time.time() - get_last_backup_time() >= BACKUP_INTERVAL:
        run_backup_async()

startup_backup_check()

# バックアップ中かどうかのフラグ（グローバル）
is_backup_running = False
def backup_all_tables():
    global is_backup_running

    if is_backup_running:
        print("⚠️ バックアップはすでに実行中です。スキップします。")
        return

    is_backup_running = True
    print(f"✅ バックアップ開始...（{datetime.now()}）")

    try:
        sheet = get_sheet_client()  # ← あなたのGoogle Sheets認証関数
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for table in TABLES:
            try:
                print(f"📄 テーブル `{table}` の処理中...")
                worksheet = sheet.worksheet(table)

                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                column_names = [desc[0] for desc in cursor.description]

                worksheet.clear()
                data = [column_names] + [list(row) for row in rows]
                worksheet.update('A1', data)

            except Exception as e:
                print(f"⚠️ エラー（{table}）: {e}")
                continue

        update_backup_time()
        print(f"✅ バックアップ完了（{datetime.now()}）")

    except Exception as e:
        print(f"❌ バックアップ全体エラー: {e}")

    finally:
        is_backup_running = False
        if conn:
            conn.close()

def backup_on_post(force=False):
    if force or (time.time() - get_last_backup_time() >= BACKUP_INTERVAL):
        run_backup_async()

class User:
    def _init_(self, id_, name, password):
        self.id = id_
        self.name = name
        self.password = password
    def is_authenticated(self): return True
    def is_active(self): return True
    def is_anonymous(self): return True
    def get_id(self): return str(self.id)
@login_manager.user_loader

def connect_db():
    conn = sqlite3.connect('miyakeiba_app.db')
    conn.row_factory = sqlite3.Row
    return conn

def hash_passward(password):
    return hashlib.sha256(passward.encode()).hexdigest()

def set_inistial_passwords(conn):
    cursor = conn.cursor()
    users = cursor.execute("SELECT id FROM users").fetchall()
    for user in users:
        user_id = user[0]
        initial_password = hash_password(f"user{user_id}")
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (initial_password, user_id))
    conn.commit()

class HolidayCalendar(calendar.HTMLCalendar):
    def formatday(self, day, weekday):
        if day == 0:
            return '<td class="noday">&nbsp;</td>'
        
        current_date = date(self.year, self.month, day)
        is_holiday = jpholiday.is_holiday(current_date)

        classes = ['weekday']
        if weekday == 5:
            classes.append('sat')
        elif weekday == 6:
            classes.append('sun')
        if is_holiday:
            classes.append('holiday')

        class_str = ' '.join(classes)
        return f'<td class="{class_str}">{day}</td>'
    
    def formatmonth(self, year, month, withyear=True):
        self.year = year
        self.month = month
        weeks = self.monthdays2calendar(year, month)

        html = []
        html.append('<table class="calendar-table">')  # ← ここでクラス付与
        html.append('\n' + self.formatmonthname(year, month, withyear=withyear))
        html.append('\n' + self.formatweekheader())

        for week in weeks:
            html.append('\n' + self.formatweek(week))

        html.append('\n</table>')
        return ''.join(html)
    
    def formatday(self, day, weekday):
        if day == 0:
            return '<td class="noday">&nbsp;</td>'
        
        current_date = date(self.year, self.month, day)
        today = date.today()
        is_holiday = jpholiday.is_holiday(current_date)

        classes = ['weekday']
        if weekday == 5:
            classes.append('sat')
        elif weekday == 6:
            classes.append('sun')
        if is_holiday:
            classes.append('holiday')
        if current_date == today:
            classes.append('today')

        class_str = ' '.join(classes)
        return f'<td class="{class_str}"><span class="day-number">{day}</span></td>'

def get_events_for_month(year, month):
    conn = connect_db()
    cursor = conn.cursor()
    
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1)
    else:
        last_day = date(year, month + 1, 1)

    first_day_str = first_day.strftime("%Y-%m-%d")
    last_day_str = last_day.strftime("%Y-%m-%d")

    query = """
        SELECT id, race_date, race_place, race_ground, race_distance, race_number, race_grade, race_name, start_time
        FROM race_schedule
        WHERE race_date >= ? AND race_date < ?
    """

    cursor.execute(query, (first_day_str, last_day_str))
    rows = cursor.fetchall()
    conn.close()

    events = {}
    for row in rows:
        date_str = row['race_date']
        day = int(date_str.split("-")[2])

        # 月日形式の加工（例：07/15）
        display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d")

        if day not in events:
            events[day] = []

        events[day].append({
            'id': row['id'],
            'race_date': row['race_date'],               # 元のYYYY-MM-DD
            'race_date_display': display_date,           # 表示用：MM/DD
            'race_place': row['race_place'],
            'race_ground': row['race_ground'],
            'race_distance': row['race_distance'],
            'race_number': row['race_number'],
            'race_grade': row['race_grade'],
            'race_name': row['race_name'],
            'start_time': row['start_time']
        })

    return events

def get_this_week_races():
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, race_date, race_name, race_place, race_ground, race_distance, race_grade
        FROM race_schedule
        WHERE race_date BETWEEN ? AND ?
        ORDER BY race_date, start_time
    """,(start_of_week.isoformat(), end_of_week.isoformat()))
    rows = cursor.fetchall()
    conn.close()
    formatted_races = []
    for row in rows:
        date_obj = datetime.strptime(row["race_date"], "%Y-%m-%d")
        weekday_jp = JAPANESE_WEEKDAYS[date_obj.weekday()]
        formatted_date = f"{date_obj.strftime('%m/%d')}（{weekday_jp}）"
        formatted_races.append({
            "id": row["id"],
            "race_date_display": formatted_date,
            "race_name": row["race_name"],
            "race_place": row["race_place"],
            "race_ground": row["race_ground"],
            "race_distance": row["race_distance"],
            "race_grade": row["race_grade"]
        })
    return formatted_races

@app.route('/')
def home():
    year = request.args.get('year', default=datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.now().month, type=int)
    
    events = get_events_for_month(year, month)

    cal = HolidayCalendar(firstweekday=0)
    calendar_html = cal.formatmonth(year,month)

    prev_month = month - 1
    prev_year = year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    next_month = month + 1
    next_year = year
    if next_month == 13:
        next_month = 1
        next_year += 1

    start_date = f"{year}-{month:02d}-01"
    end_day = monthrange(year, month)[1]
    end_date = f"{year}-{month:02d}-{end_day}"

    conn = connect_db()
    cur = conn.cursor()
    query = """
        SELECT
            username,
            COUNT(*) AS total_races,
            SUM(score) AS total_score,
            SUM(CASE WHEN honmeiba_rank = 1 THEN 1 ELSE 0 END) AS first,
            SUM(CASE WHEN honmeiba_rank = 2 THEN 1 ELSE 0 END) AS second,
            SUM(CASE WHEN honmeiba_rank = 3 THEN 1 ELSE 0 END) AS third,
            SUM(CASE WHEN honmeiba_rank BETWEEN 4 AND 5 THEN 1 ELSE 0 END) AS bbs,
            SUM(CASE WHEN honmeiba_rank = 0 THEN 1 ELSE 0 END) AS out_of_place,
            ROUND(AVG(CASE WHEN honmeiba_rank = 1 THEN 1.00 ELSE 0 END), 4) AS win_rate,
            ROUND(AVG(CASE WHEN honmeiba_rank BETWEEN 1 AND 3 THEN 1.00 ELSE 0 END), 4) AS placing_bets_rate
        FROM raise_horse rh
        JOIN race_schedule rs ON rh.race_id = rs.id
        WHERE rs.race_date BETWEEN ? AND ?
        GROUP BY username
        ORDER BY total_score DESC
    """
    cur.execute(query, (start_date, end_date))
    users = cur.fetchall()
    conn.close()

    races = get_this_week_races()
    
    return render_template('home.html', calendar_html=calendar_html, year=year, month=month,prev_year=prev_year,prev_month=prev_month,next_year=next_year,next_month=next_month,events=events,users=users,races=races)


@app.route('/insert_race', methods=['GET', 'POST'])
def insert_race():
    if request.method == 'POST':
        race_dates = request.form.getlist('race_date[]')
        race_places = request.form.getlist('race_place[]')
        race_ground = request.form.getlist('race_ground[]')
        race_distance = request.form.getlist('race_distance[]')
        race_numbers = request.form.getlist('race_number[]')
        race_grades = request.form.getlist('race_grade[]')
        race_names = request.form.getlist('race_name[]')
        start_times = request.form.getlist('start_time[]')

        conn = connect_db()
        cursor = conn.cursor()

        for i in range(len(race_dates)):
            cursor.execute("""
                INSERT INTO race_schedule (race_date, race_place, race_number, race_grade, race_name, start_time, race_ground, race_distance)
                VALUES (?,?,?,?,?,?,?,?)
            """,(
                race_dates[i],
                race_places[i],
                race_numbers[i] if race_numbers[i] else None,
                race_grades[i],
                race_names[i],
                start_times[i] if start_times[i] else None,
                race_ground[i],
                race_distance[i]
            ))

        conn.commit()
        conn.close()

        return redirect('/insert_race')
    
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, race_date, race_place, race_ground, race_distance, race_number, race_grade, race_name, start_time
        FROM race_schedule
        ORDER BY race_date DESC
    """)
    rows = cursor.fetchall()
    backup_on_post(force=True)
    conn.close()

    races = []
    for row in rows:
        races.append({
            "id": row['id'],
            "race_date": row['race_date'],
            "race_place": row['race_place'],
            "race_ground": row['race_ground'],
            "race_distance": row['race_distance'],
            "race_number": row['race_number'],
            "race_grade": row['race_grade'],
            "race_name": row['race_name'],
            "start_time": row['start_time']
        })
    
    races.sort(key=lambda x: x['race_date'], reverse=True)
    races = races[1:]

    return render_template('insert_race.html', races=races)

@app.route('/delete_race', methods=['POST'])
def delete_race():
    race_id = request.form.get('race_id')

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM race_schedule WHERE id = ?", (race_id,))
    conn.commit()
    backup_on_post(force=True)
    conn.close()

    return redirect('/insert_race')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = connect_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user is not None:
            print(dict(user))
        else:
            flash("ユーザーが見つかりません")
            return render_template('login.html')

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect('/')
        else:
            flash("ユーザー名またはパスワードが違います")
            return render_template('login.html')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        hashed_pw = generate_password_hash(password)

        conn = connect_db()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, hashed_pw, 'user'))
            backup_on_post()
            conn.commit()
        except sqlite3.IntegrityError:
            flash("ユーザー名は既に使われています")
            return redirect('/register')
        finally:
            conn.close()

        flash("登録に成功しました。ログインしてください。")
        run_backup_async()
        return redirect('/login')

    return render_template('register.html')

@app.route('/entry_form', methods=['GET', 'POST'])
def entry_form():
    conn = connect_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        race_id = request.form['race_id']
        horse_names = request.form.getlist('horse_name[]')
        jockeys = request.form.getlist('jockey[]')

        try:
            cursor.execute("DELETE FROM race_entries WHERE race_id = ?", (race_id,))

            for i, horse_name in enumerate(horse_names):
                horse_name = horse_name.strip()
                jockey = jockeys[i].strip() if i < len(jockeys) else ''
                if horse_name and jockey:
                    cursor.execute("""
                        INSERT INTO race_entries (race_id, horse_number, horse_name, jockey)
                        VALUES (?, ?, ?, ?)
                    """, (race_id, i + 1, horse_name, jockey))

            conn.commit()
            flash("出馬表を登録しました")
            return redirect('/entry_form')

        except Exception as e:
            conn.rollback()
            flash(f"登録エラー: {e}")
            return redirect('/entry_form')

        finally:
            conn.close()

    cursor.execute("""
        SELECT id, race_date, race_place, race_number, race_name
        FROM race_schedule
        ORDER BY race_date DESC
    """)
    races = cursor.fetchall()
    races = races[1:]  # 必要なら

    backup_on_post(force=True)
    conn.close()

    return render_template('entry_form.html', races=races)

@app.route('/entries/<int:race_id>', methods=['GET', 'POST'])
def show_entries(race_id):
    conn = connect_db()
    cursor = conn.cursor()

    # レース情報取得
    cursor.execute("SELECT id, race_date, race_place, race_name, start_time FROM race_schedule WHERE id = ?", (race_id,))
    race = cursor.fetchone()

    if not race:
        conn.close()
        flash("指定されたレースが見つかりません")
        return redirect('/')

    race = dict(race)

    race_datetime_str = f"{race['race_date']} {race['start_time']}"  # "YYYY-MM-DD HH:MM"
    try:
        race_datetime = datetime.strptime(race_datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        flash("レースの日時情報に誤りがあります。")
        return redirect('/', current_path=request.path)

    voting_deadline = race_datetime - timedelta(minutes=1)
    now = datetime.now()

    is_closed = now >= voting_deadline

    # POST処理（本命馬登録）
    if request.method == 'POST':
        honmeiba = request.form.get('honmeiba')
        if honmeiba:
            cursor.execute("""
                INSERT INTO raise_horse(race_id, username, honmeiba)
                VALUES(?,?,?)
                ON CONFLICT(race_id, username) DO UPDATE SET honmeiba=excluded.honmeiba
            """, (race_id, session.get('username'), honmeiba))
            backup_on_post()
            conn.commit()

    # 出馬表取得
    cursor.execute("SELECT horse_name, jockey FROM race_entries WHERE race_id = ?", (race_id,))
    entries = cursor.fetchall()
    conn.close()

    return render_template('entries.html', entries=entries, race=race, selected_race_id=race_id, is_closed=is_closed)

@app.route('/mypage')
def mypage():
    if 'username' not in session:
        flash('ログインが必要です')
        return redirect(url_for('login'))
    
    username = session['username']
    conn = connect_db()
    cursor = conn.cursor()

    # 成績一覧データ（過去の参加レース）
    cursor.execute("""
        SELECT r.race_date, r.race_place, r.race_name, h.honmeiba, h.honmeiba_rank, h.score
        FROM raise_horse h
        JOIN race_schedule r ON h.race_id = r.id
        WHERE h.username = ?
        ORDER BY r.race_date DESC
    """, (username,))
    entries = cursor.fetchall()

    # 個人成績集計（横一列に表示する要約）
    cursor.execute("""
        SELECT
            COUNT(*) AS total_races,
            SUM(score) AS total_score,
            SUM(CASE WHEN honmeiba_rank = 1 THEN 1 ELSE 0 END) AS first,
            SUM(CASE WHEN honmeiba_rank = 2 THEN 1 ELSE 0 END) AS second,
            SUM(CASE WHEN honmeiba_rank = 3 THEN 1 ELSE 0 END) AS third,
            SUM(CASE WHEN honmeiba_rank BETWEEN 4 AND 5 THEN 1 ELSE 0 END) AS bbs,
            SUM(CASE WHEN honmeiba_rank = 0 THEN 1 ELSE 0 END) AS out_of_place,
            ROUND(AVG(CASE WHEN honmeiba_rank = 1 THEN 1.00 ELSE 0 END), 4) AS win_rate,
            ROUND(AVG(CASE WHEN honmeiba_rank BETWEEN 1 AND 3 THEN 1.00 ELSE 0 END), 4) AS placing_bets_rate
        FROM raise_horse
        WHERE username = ?
    """, (username,))
    row = cursor.fetchone()

    conn.close()

    user_stats = None
    if row and row[0] > 0:
        user_stats = {
            "total_races": row[0],
            "total_score": row[1],
            "first": row[2],
            "second": row[3],
            "third": row[4],
            "bbs": row[5],
            "out_of_place": row[6],
            "win_rate": row[7],
            "placing_bets_rate": row[8],
        }

    return render_template('mypage.html', username=username, entries=entries, user=user_stats)

@app.route('/result_input/<int:race_id>', methods=['GET', 'POST'])
def result_input(race_id):
    conn = connect_db()
    cursor = conn.cursor()

    if request.method == 'POST':
        first_place = request.form.get('first_place')
        second_place = request.form.get('second_place')
        third_place = request.form.get('third_place')
        fourth_place = request.form.get('fourth_place')
        fifth_place = request.form.get('fifth_place')
        odds_first = request.form.get('odds_first')
        odds_second = request.form.get('odds_second')
        odds_third = request.form.get('odds_third')

        cursor.execute("""
            INSERT INTO race_result (
                race_id, first_place, second_place, third_place,
                fourth_place, fifth_place, odds_first, odds_second, odds_third
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(race_id) DO UPDATE SET
                first_place = excluded.first_place,
                second_place = excluded.second_place,
                third_place = excluded.third_place,
                fourth_place = excluded.fourth_place,
                fifth_place = excluded.fifth_place,
                odds_first = excluded.odds_first,
                odds_second = excluded.odds_second,
                odds_third = excluded.odds_third
        """, (
            race_id, first_place, second_place, third_place,
            fourth_place, fifth_place, odds_first, odds_second, odds_third
        ))

        update_scores(conn, race_id)

        backup_on_post(force=True)
        conn.commit()
        conn.close()
        flash("レース結果を登録しました")
        return redirect(url_for('show_entries', race_id=race_id))

    # GETの場合はレース名を取得してフォーム表示
    cursor.execute("SELECT race_name FROM race_schedule WHERE id = ?", (race_id,))
    race = cursor.fetchone()
    cursor.execute("SELECT horse_name FROM race_entries WHERE race_id = ?", (race_id,))
    horses = [row['horse_name'] for row in cursor.fetchall()]
    conn.close()

    return render_template('insert_result.html', race=race, race_id=race_id, horses=horses)

# @app.route('/update_scores/<int:race_id>', methods=['POST'])
def update_scores(conn, race_id):
    cur = conn.cursor()

    # レース結果取得
    cur.execute("""
        SELECT first_place, second_place, third_place,
        fourth_place, fifth_place,
        odds_first, odds_second, odds_third
        FROM race_result WHERE race_id = ?
    """, (race_id,))
    res = cur.fetchone()
    if not res:
        flash("レース結果が未登録です")
        return
    result = dict(res)

    # 本命馬提出データ取得
    cur.execute("""
        SELECT username, honmeiba FROM raise_horse WHERE race_id = ?
    """, (race_id,))
    rows = cur.fetchall()

    for username, honmeiba in rows:
        rank = 0
        odds = None
        score = 0

        if honmeiba == result['first_place']:
            rank = 1
            odds = result['odds_first']
            score = round(odds * 10)
        elif honmeiba == result['second_place']:
            rank = 2
            odds = result['odds_second']
            score = round(odds * 3)
        elif honmeiba == result['third_place']:
            rank = 3
            odds = result['odds_third']
            score = round(odds * 1)
        elif honmeiba == result['fourth_place']:
            rank = 4
        elif honmeiba == result['fifth_place']:
            rank = 5

        cur.execute("""
            UPDATE raise_horse
            SET honmeiba_rank = ?, honmeiba_odds = ?, score = ?
            WHERE race_id = ? AND username = ?
        """, (rank, odds, score, race_id, username))

        if rank == 1:
            cur.execute("UPDATE users set first = first + 1, score = score + ? WHERE username = ?", (score, username))
        elif rank == 2:
            cur.execute("UPDATE users SET second = second + 1, score = score + ? WHERE username = ?", (score, username))
        elif rank == 3:
            cur.execute("UPDATE users SET third = third + 1, score = score + ? WHERE username = ?", (score, username))
        elif rank in [4, 5]:
            cur.execute("UPDATE users SET bbs = bbs + 1 WHERE username = ?", (username,))
        else:
            cur.execute("UPDATE users SET out_of_place = out_of_place + 1 WHERE username = ?", (username,))
    
    cur.execute("SELECT username, first, second, third FROM users")
    for user in cur.fetchall():
        username = user["username"]
        first = user["first"]
        second = user["second"]
        third = user["third"]

        # raise_horseから提出回数を取得
        cur.execute("SELECT COUNT(*) FROM raise_horse WHERE username = ?", (username,))
        total_entries = cur.fetchone()[0]

        if total_entries > 0:
            win_rate = first / total_entries
            placing_rate = (first + second + third) / total_entries
        else:
            win_rate = 0
            placing_rate = 0

        cur.execute("""
            UPDATE users
            SET win_rate = ?, placing_bets_rate = ?
            WHERE username = ?
        """, (win_rate, placing_rate, username))

    backup_on_post()
    conn.commit()
    flash("得点とユーザー情報を更新しました")

@app.route('/race_result/<int:race_id>', methods=['GET', 'POST'])
def show_race_result(race_id):
    conn = connect_db()
    cur = conn.cursor()

    # GET時はフォーム表示のために馬一覧を渡す
    cur.execute("SELECT horse_name FROM race_entries WHERE race_id = ?", (race_id,))
    horses = [row['horse_name'] for row in cur.fetchall()]
    cur.execute("SELECT * FROM race_result WHERE race_id = ?", (race_id,))
    result_row = cur.fetchone()
    result = dict(result_row) if result_row else {
        'first_place': '',
        'second_place': '',
        'third_place': '',
        'fourth_place': '',
        'fifth_place': '',
        'odds_first': '',
        'odds_second': '',
        'odds_third': ''
    }
    cur.execute("SELECT race_name FROM race_schedule WHERE id = ?", (race_id,))
    race = cur.fetchone()
    cur.execute("""SELECT username, honmeiba, score FROM raise_horse WHERE race_id = ?""", (race_id,))
    scores = cur.fetchall()
    sorted_scores = sorted(scores, key=lambda x: x['score'], reverse=True)
    ranked_scores = []
    prev_score = None
    rank = 0
    count = 0

    for row in sorted_scores:
        count += 1
        if row['score'] != prev_score:
            rank = count
        ranked_scores.append({
            'rank': rank,
            'username': row['username'],
            'honmeiba': row['honmeiba'],
            'score': row['score']
        })
        prev_score = row['score']
    conn.close()

    return render_template('race_result.html', race_id=race_id, horses=horses, race=race, result=result, scores=ranked_scores)

@app.route('/allusers')
def allusers():
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT race_grade FROM race_schedule ORDER BY race_grade")
    grades = [row[0] for row in cur.fetchall() if row[0] not in ('race_grade',)]
    
    cur.execute("SELECT DISTINCT race_place FROM race_schedule ORDER BY race_place")
    places = [row[0] for row in cur.fetchall() if row[0] not in ('race_place',)]

    cur.execute("""
        SELECT
            username,
            COUNT(*) AS total_races,
            SUM(score) AS total_score,
            SUM(CASE WHEN honmeiba_rank = 1 THEN 1 ELSE 0 END) AS first,
            SUM(CASE WHEN honmeiba_rank = 2 THEN 1 ELSE 0 END) AS second,
            SUM(CASE WHEN honmeiba_rank = 3 THEN 1 ELSE 0 END) AS third,
            SUM(CASE WHEN honmeiba_rank BETWEEN 4 AND 5 THEN 1 ELSE 0 END) AS bbs,
            SUM(CASE WHEN honmeiba_rank = 0 THEN 1 ELSE 0 END) AS out_of_place,
            ROUND(AVG(CASE WHEN honmeiba_rank = 1 THEN 1.00 ELSE 0 END), 4) AS win_rate,
            ROUND(AVG(CASE WHEN honmeiba_rank BETWEEN 1 AND 3 THEN 1.00 ELSE 0 END), 4) AS placing_bets_rate
        FROM raise_horse rh
        JOIN race_schedule rs ON rh.race_id = rs.id
        GROUP BY username
        ORDER BY total_score DESC
    """)
    users = cur.fetchall()
    conn.close()
    return render_template('alluserscore.html', all_users=users, grades=grades, places=places)

@app.route('/filtered_users')
def filtered_users():
    grade = request.args.get('race_type')  # e.g., G1
    venue = request.args.get('venue')      # e.g., 東京

    conn = connect_db()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT race_grade FROM race_schedule ORDER BY race_grade")
    grades = [row[0] for row in cur.fetchall() if row[0] not in ('race_grade',)]
    
    cur.execute("SELECT DISTINCT race_place FROM race_schedule ORDER BY race_place")
    places = [row[0] for row in cur.fetchall() if row[0] not in ('race_place',)]

    all_query = """
        SELECT
            username,
            COUNT(*) AS total_races,
            SUM(score) AS total_score,
            SUM(CASE WHEN honmeiba_rank = 1 THEN 1 ELSE 0 END) AS first,
            SUM(CASE WHEN honmeiba_rank = 2 THEN 1 ELSE 0 END) AS second,
            SUM(CASE WHEN honmeiba_rank = 3 THEN 1 ELSE 0 END) AS third,
            SUM(CASE WHEN honmeiba_rank BETWEEN 4 AND 5 THEN 1 ELSE 0 END) AS bbs,
            SUM(CASE WHEN honmeiba_rank = 0 THEN 1 ELSE 0 END) AS out_of_place,
            ROUND(AVG(CASE WHEN honmeiba_rank = 1 THEN 1.00 ELSE 0 END), 4) AS win_rate,
            ROUND(AVG(CASE WHEN honmeiba_rank BETWEEN 1 AND 3 THEN 1.00 ELSE 0 END), 4) AS placing_bets_rate
        FROM raise_horse rh
        JOIN race_schedule rs ON rh.race_id = rs.id
        GROUP BY username
        ORDER BY total_score DESC
    """
    cur.execute(all_query)
    all_users = cur.fetchall()

    filtered_query = """
        SELECT
            username,
            COUNT(*) AS total_races,
            SUM(score) AS total_score,
            SUM(CASE WHEN honmeiba_rank = 1 THEN 1 ELSE 0 END) AS first,
            SUM(CASE WHEN honmeiba_rank = 2 THEN 1 ELSE 0 END) AS second,
            SUM(CASE WHEN honmeiba_rank = 3 THEN 1 ELSE 0 END) AS third,
            SUM(CASE WHEN honmeiba_rank BETWEEN 4 AND 5 THEN 1 ELSE 0 END) AS bbs,
            SUM(CASE WHEN honmeiba_rank = 0 THEN 1 ELSE 0 END) AS out_of_place,
            ROUND(AVG(CASE WHEN honmeiba_rank = 1 THEN 1.00 ELSE 0 END), 4) AS win_rate,
            ROUND(AVG(CASE WHEN honmeiba_rank BETWEEN 1 AND 3 THEN 1.00 ELSE 0 END), 4) AS placing_bets_rate
        FROM raise_horse rh
        JOIN race_schedule rs ON rh.race_id = rs.id
        WHERE 1=1
    """
    params = []
    if grade:
        filtered_query += " AND rs.race_grade = ?"
        params.append(grade)
    if venue:
        filtered_query += " AND rs.race_place = ?"
        params.append(venue)

    filtered_query += " GROUP BY username ORDER BY total_score DESC"

    cur.execute(filtered_query, params)
    filtered_users = cur.fetchall()
    conn.close()

    return render_template('alluserscore.html', all_users=all_users, filtered_users=filtered_users, grades=grades, places=places)

if __name__ == '__main__':
    app.run(debug=False)
