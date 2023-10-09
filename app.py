from flask import Flask,render_template,request,redirect, url_for, send_file, flash, session
from flask_session import Session
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import hashlib
from rq import Queue
from redis import Redis
from flask import request, jsonify
from time import sleep

from rq import Queue
from worker import conn
from task import RQ_worker
import os
import glob
import pandas as pd
from io import BytesIO
import datetime

q = Queue(connection=conn, default_timeout=3600)
rq_worker = RQ_worker()
users_ref_admin_check = rq_worker.db_ref.child('users').get()
if users_ref_admin_check == None or (type(users_ref_admin_check) == dict and 'admin' not in users_ref_admin_check):
    rq_worker.db_ref.child('users').child('admin').set({'role':'admin','password':hashlib.sha256('1234'.encode('utf-8')).hexdigest()})

app = Flask(__name__)
app.secret_key = 'my_secret_number23_for_scraping_hehenrk'
app.config['SESSION_TYPE'] = 'filesystem' 
Session(app)


# Custom logout route
@app.route('/logout', methods=['POST'])
def logout():
    session.pop(session.get('user'),None)
    session.pop(session.get('logedin'),None)
    session.pop(session.get('role'),None)
    return redirect(url_for('login'))


# Custom login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        users_ref = rq_worker.db_ref.child('users').get()
        # Check if the username exists and the password is correct
        if username in users_ref and hashlib.sha256(password.encode('utf-8')).hexdigest() == users_ref.get(username).get('password'):
            session['user'] = username  # Store the username in the session
            session['logedin'] = True
            session['role'] = users_ref.get(username).get('role')
            return redirect(url_for('main'))
        else:
            flash('User or password is incorrect')
    
    return render_template('login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin_page():
    if not(session.get('logedin')) or session.get('role')!='admin':
        flash('Please login to access your account.')
        return redirect(url_for('login'))
    users_ref = rq_worker.db_ref.child('users')
    if request.method == 'POST':
        username = request.form['username']
        role = request.form['role']
        password = request.form['password']
        print({"username": username, "password": password})
        if 'users' == username:
            flash('Username cannot be users')
        else:
            users_ref.child(username).set({'role': role,'password':hashlib.sha256(password.encode('utf-8')).hexdigest()})
    users_list = [i for i in users_ref.get()]
    return render_template('admin.html', users=users_list)


@app.route('/', methods=['GET'])
# @auth.login_required
def main():
    if not(session.get('logedin')):
        flash('Please login to access your account.')
        return redirect(url_for('login'))
    excel_files = []
    try:
        users_ref = rq_worker.db_ref.child(session.get('user')).get()
        print(users_ref)
        excel_files = sorted([(users_ref.get(i).get('handling').get('time'),
                        i,
                        users_ref.get(i).get('handling').get('status')) 
                        for i in users_ref.keys()], reverse = True)
    except Exception as exp:
        print(exp)
        return render_template('hello_updated.html',excel_files=excel_files, role = session.get('role'))
    return render_template('hello_updated.html',excel_files=excel_files, role = session.get('role'))



# app.config['RQ_DSN'] = 'redis://localhost:6379/0'
# redis_conn = Redis.from_url(app.config['RQ_DSN'])
# rq = Queue(connection=redis_conn)

@app.route('/scrap-file', methods=['GET','POST'])
# @auth.login_required
def scrap_file():
    if not(session.get('logedin')):
        flash('Please login to access your account.')
        return redirect(url_for('login'))
    # data = request.json  # Assuming JSON data in the request
    
    # Enqueue a task to be processed asynchronously
    try:
        print(request.get_json())
        file = request.get_json()['file']
        url_list = rq_worker.db_ref.child(session.get('user')).child(file).child('handling')
        users_ref = url_list.get()
        print(users_ref)
        if 'initialized' in users_ref.get('status'):
            return 'This file is not recommended for Initializing data. You shuold start Webliner.'
        url_list.child('status').set('File is in queue for initializing data.')
        job = q.enqueue(rq_worker.scrap_data, file, user = session.get('user'))  # Where 'process_data' is your task function
        return "File enqueued for Initializing data."
    except Exception as exp:
        print('exp', exp)
        return f'error: {exp}'
    

@app.route('/comment-file', methods=['GET','POST'])
# @auth.login_required
def comment_file():
    if not(session.get('logedin')):
        flash('Please login to access your account.')
        return redirect(url_for('login'))
    # data = request.json  # Assuming JSON data in the request
    
    # Enqueue a task to be processed asynchronously
    try:
        print(request.get_json())
        file = request.get_json()['file']
        url_list = rq_worker.db_ref.child(session.get('user')).child(file).child('handling')
        users_ref = url_list.get()
        if 'webliners have been generated' in users_ref.get('status'):
            return 'This file is not recommended for webliners generation. You shuold download it.'
        url_list.child('status').set('File is in queue for generating webliner.')
        job = q.enqueue(rq_worker.comment_data, file, user = session.get('user'))  # Where 'process_data' is your task function
        return "File passed for webliners generation."
    except Exception as exp:
        print('exp', exp)
        return f'error: {exp}'


@app.route('/upload', methods=['POST'])
# @auth.login_required
def upload_file():
    if not(session.get('logedin')):
        flash('Please login to access your account.')
        return redirect(url_for('login'))
    # if 'excel_file' not in request.files:
    #     return 'No file part'
    
    file = request.files['excel_file']

    # if file.filename == '':
    #     return 'No selected file'
    
    if file:
        # Assuming the uploaded file is in Excel format (e.g., .xlsx)
        if file.filename.endswith('.xlsx'):
            tmp_resp = rq_worker.db_ref.child(session.get('user')).get()
            if type(tmp_resp) == dict and file.filename.replace('.xlsx','') in tmp_resp.keys():
                flash('File already uploaded')
                return redirect(url_for('main'))
            url_file = pd.read_excel(file)
            
            if 'website' not in url_file.columns:
                flash('Column name website not found')
                return redirect(url_for('main'))
            new_url = {x : {'link':'https://'+i.replace('https://','').replace('http://','')} for x, i in enumerate(url_file['website'])}
            print('new_url', new_url)
            time_upload = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            users_ref = rq_worker.db_ref.child(session.get('user')).child(file.filename.replace('.xlsx',''))
            users_ref.set(new_url)
            users_ref = rq_worker.db_ref.child(session.get('user')).child(file.filename.replace('.xlsx','')).child('handling')
            users_ref.set({'status': 'File uploaded successfully.', 'time': time_upload})
            # Now 'df' contains the data from the uploaded Excel file as a Pandas DataFrame
            # You can perform various operations on 'df' here
            # return 'File uploaded successfully. You can start scraping the urls.'
        else:
            flash('Please upload .xlsx file format')
            return redirect(url_for('main'))
    return redirect(url_for('main'))

@app.route('/check-status', methods=['POST'])
# @auth.login_required
def check_status():
    if not(session.get('logedin')):
        flash('Please login to access your account.')
        return redirect(url_for('login'))
    comment = 0
    url = 0
    scrap = 0
    
    file = request.get_json()['file']
    users_ref = rq_worker.db_ref.child(session.get('user')).child(file).get()
    url = len(users_ref.keys())-1
    for i in users_ref.keys():
        if i == 'handling' or users_ref.get(i) == '' or users_ref.get(i).get('text') == None:
            continue
        else:
            if users_ref.get(i).get('text') != None:
                scrap += 1
            if users_ref.get(i).get('comment') != None:
                comment += 1
    if users_ref.get('handling') == None:
        response_ = 'file not found'
    else:
        response_ = users_ref.get('handling').get('status')
    if 'generating webliner' in response_ and comment != 0:
        response_ += f'{comment} out of {scrap} has been completed with webliners.'
    elif 'initializing data' in response_ and scrap != 0:
        response_ += f'{scrap} out of {url} has been initialized completely.'
    return response_

@app.route('/download', methods=['POST'])
# @auth.login_required
def download_file():
    if not(session.get('logedin')):
        flash('Please login to access your account.')
        return redirect(url_for('login'))
    print(request.form.get('file'))
    # Replace 'path/to/your/file' with the actual path to your file
    file = request.form.get('file')
    db_data = rq_worker.db_ref.child(session.get('user')).child(file).get()
    try:
        del db_data['handling']
    except:
        pass
    # print(data)
    
    url = []
    comment = []
    # print(db_data.keys())
    # print(db_data)
    for i in db_data.keys():
        # print(i)
        # print(db_data[i].get('comment'))
        url.append(db_data[i].get('link'))
        comment.append(db_data[i].get('comment'))
    data = {'url': url, 'comment': comment}

    df = pd.DataFrame(data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Sheet1', index=False)

    output.seek(0)
    response_headers = {
        'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'Content-Disposition': 'attachment; filename=data.xlsx',
    }
    return send_file(output, as_attachment=True, download_name=file+'_webliners.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
   app.run(host = '0.0.0.0', debug = True, port=int(os.environ.get("PORT", 8080)))


