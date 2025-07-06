from flask import Flask,render_template,request,redirect, session, url_for, flash # type: ignore
from flask_login import LoginManager, login_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash # type: ignore
import calendar
import datetime
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

app = Flask(__name__)
SHEET_NAME = "miyakeiba_backup"
TABLES = ['race_entries', 'race_result', 'race_schedule', 'raise_horse', 'sqlite_sequence', 'users', 'timestamp']
BACKUP_INTERVAL = 600
TIMESTAMP_FILE = "last_backup.txt"
DB_NAME = "miyakeiba_app.db"
login_manager = LoginManager()
login_manager.init_app(app)
def load_backup_from_sheet():
    print("📥 スプレッドシートからバックアップを読み込み中...")

    # 認証とシート接続
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])  # 環境変数から読み込み
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open(SHEET_NAME)
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
def get_sheet_client():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME)

# バックアップ中かどうかのフラグ（グローバル）
is_backup_running = False
def backup_all_tables():
    global is_backup_running

    if is_backup_running:
        print("⚠️ バックアップはすでに実行中です。スキップします。")
        return

    is_backup_running = True
    print(f"✅ バックアップ開始...（{datetime.now()}）")

    conn = None
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

        print(f"✅ バックアップ完了（{datetime.now()}）")

    except Exception as e:
        print(f"❌ バックアップ全体エラー: {e}")

    finally:
        is_backup_running = False
        conn.close()
def run_backup_async():
    thread = threading.Thread(target=backup_all_tables)
    thread.start()

@app.template_filter('datetimeformat')
def datetimeformat(value, format="%m/%d"):
    return datetime.datetime.strptime(value, "%Y-%m-%d").strftime(format)

    conn.close()
    update_backup_time()
    load_backup_from_sheet()
    print("✅ 全テーブルのバックアップ完了！")
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
        worksheet.insert_row([now], 1)
    except Exception as e:
        print(f"⚠️ タイムスタンプ更新エラー: {e}")
def startup_backup_check():
    if time.time() - get_last_backup_time() >= BACKUP_INTERVAL:
        run_backup_async()
startup_backup_check()
app.secret_key = 'your_secret_key'
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
        
        date = datetime.date(self.year, self.month, day)
        is_holiday = jpholiday.is_holiday(date)

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
        
        date = datetime.date(self.year, self.month, day)
        today = datetime.date.today()
        is_holiday = jpholiday.is_holiday(date)

        classes = ['weekday']
        if weekday == 5:
            classes.append('sat')
        elif weekday == 6:
            classes.append('sun')
        if is_holiday:
            classes.append('holiday')
        if date == today:
            classes.append('today')

        class_str = ' '.join(classes)
        return f'<td class="{class_str}"><span class="day-number">{day}</span></td>'

def get_events_for_month(year, month):
    conn = connect_db()
    cursor = conn.cursor()
    
    first_day = datetime.date(year, month, 1)
    if month == 12:
        last_day = datetime.date(year + 1, 1, 1)
    else:
        last_day = datetime.date(year, month + 1, 1)

    first_day_str = first_day.strftime("%Y-%m-%d")
    last_day_str = last_day.strftime("%Y-%m-%d")

    query = """
        SELECT id, race_date, race_place, race_number, race_grade, race_name, start_time
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
        display_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%m/%d")

        if day not in events:
            events[day] = []

        events[day].append({
            'id': row['id'],
            'race_date': row['race_date'],               # 元のYYYY-MM-DD
            'race_date_display': display_date,           # 表示用：MM/DD
            'race_place': row['race_place'],
            'race_number': row['race_number'],
            'race_grade': row['race_grade'],
            'race_name': row['race_name'],
            'start_time': row['start_time']
        })

    return events

@app.route('/')
def home():
    year = request.args.get('year', default=datetime.datetime.now().year, type=int)
    month = request.args.get('month', default=datetime.datetime.now().month, type=int)
    
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

    
    return render_template('main.html', calendar_html=calendar_html, year=year, month=month,prev_year=prev_year,prev_month=prev_month,next_year=next_year,next_month=next_month,events=events,users=users)


@app.route('/insert_race', methods=['GET', 'POST'])
def insert_race():
    if request.method == 'POST':
        race_dates = request.form.getlist('race_date[]')
        race_places = request.form.getlist('race_place[]')
        race_numbers = request.form.getlist('race_number[]')
        race_grades = request.form.getlist('race_grade[]')
        race_names = request.form.getlist('race_name[]')
        start_times = request.form.getlist('start_time[]')

        conn = connect_db()
        cursor = conn.cursor()

        for i in range(len(race_dates)):
            cursor.execute("""
                INSERT INTO race_schedule (race_date, race_place, race_number, race_grade, race_name, start_time)
                VALUES (?,?,?,?,?,?)
            """,(
                race_dates[i],
                race_places[i],
                race_numbers[i] if race_numbers[i] else None,
                race_grades[i],
                race_names[i],
                start_times[i] if start_times[i] else None
            ))

        conn.commit()
        conn.close()

        return redirect('/insert_race')
    
    conn = connect_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, race_date, race_place, race_number, race_grade, race_name, start_time
        FROM race_schedule
        ORDER BY race_date DESC
    """)
    rows = cursor.fetchall()
    run_backup_async()
    conn.close()

    races = []
    for row in rows:
        races.append({
            "id": row['id'],
            "race_date": row['race_date'],
            "race_place": row['race_place'],
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
    run_backup_async()
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
            run_backup_async()
            conn.commit()
        except sqlite3.IntegrityError:
            flash("ユーザー名は既に使われています")
            return redirect('/register')
        finally:
            conn.close()

        flash("登録に成功しました。ログインしてください。")
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

    run_backup_async()
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
        race_datetime = datetime.datetime.strptime(race_datetime_str, "%Y-%m-%d %H:%M")
    except ValueError:
        flash("レースの日時情報に誤りがあります。")
        return redirect('/', current_path=request.path)

    voting_deadline = race_datetime - datetime.timedelta(minutes=1)
    now = datetime.datetime.now()

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
            run_backup_async()
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

    cursor.execute("""
        SELECT r.race_date, r.race_place, r.race_name, h.honmeiba, h.honmeiba_rank, h.score
        FROM raise_horse h
        JOIN race_schedule r ON h.race_id = r.id
        WHERE h.username = ?
        ORDER BY r.race_date DESC
    """, (username,))
    entries = cursor.fetchall()
    conn.close()

    return render_template('mypage.html', username=username, entries=entries)

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

        run_backup_async()
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

    run_backup_async()
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
