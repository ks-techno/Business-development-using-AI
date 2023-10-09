from time import sleep
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
from gensim.summarization import summarize
import openai
import os
import json
import pandas as pd
import numpy as np
secret = 'openai-key'
import re
import firebase_admin
from firebase_admin import credentials, db


class RQ_worker:
    cred = credentials.Certificate('firebase-realtime-certificate-file')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'database-url'  # Replace with your project's database URL
    })

    # Create a reference to your Realtime Database
    db_ref = db.reference('/')
    def __init__(self):
        print('constructor')
        
    
    @staticmethod
    def flow(file, user):
        RQ_worker.scrap_data(file, user)
        RQ_worker.comment_data(file, user)

    @staticmethod
    def scrap_data(file, user):
        print('scraping started')
        # Simulate a time-consuming task (e.g., data processing)
        urls_list = RQ_worker.db_ref.child(user).child(file)
        urls_list.child('handling').child('status').set('initializing data.')
        urls_ref = urls_list.get()
        print('url_files_retrieved successfully.')
        print(urls_ref)
        header = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
            }
        response_dict_list = []
        for index in urls_ref.keys():
            if index == 'handling' or (type(urls_ref.get(index)) == dict and urls_ref.get(index).get('text')!=None):
                continue
            elif urls_ref.get(index).get('link')!=None and \
                urls_ref.get(index).get('link') in \
                [urls_ref.get(j).get('link') for j in urls_ref.keys() if j < index]:
                for j in urls_ref.keys():
                    if j < index and  urls_ref.get(index).get('link') == urls_ref.get(j).get('link'):
                        url_comment = RQ_worker.db_ref.child(user).child(file).child(index)
                        url_comment.set(RQ_worker.db_ref.child(user).child(file).child(j).get())
                        print(index, urls_ref.get(index).get('link'), f'copied back from {j}')
                        break
                continue
            print(f"sending response for {urls_ref.get(index).get('link')}")
            url = urls_ref.get(index).get('link')
            try:
                try:
                    response = requests.get(url)
                except Exception as exp:
                    print(exp)
                if response.status_code != 200:
                    print(f'adding header due to {response.status_code}')
                    response = requests.get(url, headers = header)
                print('response received')
                html_doc = response.text
                soup = BeautifulSoup(html_doc, 'html.parser')
                tmp_text = soup.get_text()
                tmp_text = re.sub( '\.', 'htmltag', tmp_text )
                tmp_text = re.sub( '{{.*?}}', ' ', tmp_text)
                tmp_text = re.sub( '\W', ' ', tmp_text)
                tmp_text = re.sub( 'htmltag', '.', tmp_text)
                while '  ' in tmp_text:
                    tmp_text = re.sub( '  ', ' ', tmp_text)
                print('firebase')
                url_text = RQ_worker.db_ref.child(user).child(file).child(index)
                url_text.set({'text':tmp_text, 'link': url})
                print('firebase ended')
            except Exception as exp:
                print(exp)
                url_text = RQ_worker.db_ref.child(user).child(file).child('handling').child('status')
                url_text.set('File uploaded successfully. During data loading there got an error.')
        url_text = RQ_worker.db_ref.child(user).child(file).child('handling').child('status')
        url_text.set('File data has been initialized scuccessfully.')

    @staticmethod
    def comment_data(file, user):
        # Simulate a time-consuming task (e.g., data processing)
        urls_list = RQ_worker.db_ref.child(user).child(file)
        urls_list.child('handling').child('status').set('generating webliner.')
        urls_ref = urls_list.get()
        openai.api_key = secret
        for i in urls_ref.keys():
            if i == 'handling' or (type(urls_ref.get(i)) == dict and urls_ref.get(i).get('comment')!=None):
                continue
            elif urls_ref.get(i).get('link')!=None and \
                urls_ref.get(i).get('link') in \
                [urls_ref.get(j).get('link') for j in urls_ref.keys() if j < i]:
                for j in urls_ref.keys():
                    if j < i and  urls_ref.get(i).get('link') == urls_ref.get(j).get('link'):
                        url_comment = RQ_worker.db_ref.child(user).child(file).child(i)
                        url_comment.set(RQ_worker.db_ref.child(user).child(file).child(j).get())
                        print(i, urls_ref.get(i).get('link'), f'copied back from {j}')
                        break
                continue
            time.sleep(21)
            try:
                prompt = f"""(((\n{urls_ref.get(i).get('text')}))) \nFrom the text given above find an opening line , something great about their website and start the message with 'i was really impressed with your ...' comment on their work they did for a client, or testimonial or achievement or award. I am doing outreach so i need one good response with less than 40 words only"""
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo-0613",
                    messages=[
                    {"role": "user", "content": prompt}
                    ]
                )
                url_comment = RQ_worker.db_ref.child(user).child(file).child(i)
                url_comment.set({'text':urls_ref.get(i).get('text'), 'link':urls_ref.get(i).get('link'),'comment': response.choices[0]["message"]["content"]})
                print(i, urls_ref.get(i).get('link'), 'processed')
            except openai.error.InvalidRequestError as exp1:
                print('exp in openai length error ', exp1)
                tmp_text = summarize(urls_ref.get(i).get('text'))
                if len(tmp_text)>14000:
                    print('truncated also')
                    tmp_text = tmp_text[:14000]
                prompt = f"""(((\n{tmp_text}))) \nFrom the text given above find an opening line , something great about their website and start the message with 'i was really impressed with your ...' comment on their work they did for a client, or testimonial or achievement or award. I am doing outreach so i need one good response with less than 40 words only"""
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo-0613",
                    messages=[
                    {"role": "user", "content": prompt}
                    ]
                )
                url_comment = RQ_worker.db_ref.child(user).child(file).child(i)
                url_comment.set({'text':urls_ref.get(i).get('text'), 'link':urls_ref.get(i).get('link'),'comment': response.choices[0]["message"]["content"]})
                print(i, urls_ref.get(i).get('link'), 'processed after summarizing')
            except Exception as exp:
                print('exp', exp)
                url_comment = RQ_worker.db_ref.child(user).child(file).child(i)
                url_comment.set({'text':urls_ref.get(i).get('text'), 'comment': exp })
        url_comment = RQ_worker.db_ref.child(user).child(file).child('handling').child('status')
        url_comment.set('All webliners have been generated scuccessfully.')
