import requests
import pywhatkit as kit
import smtplib
import schedule
import time

from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dotenv import dotenv_values

# Falta guardar em um csv os envios de email, pra evitar que faça um envio duplicado
# Fazer loop de pesqquisa de vários itens


# *** SCHEDULE ***
# def job():
#     print("I'm working...")

# schedule.every(1).minutes.do(job)

# while True:
#     schedule.run_pending()
#     time.sleep(1)
    

config = dotenv_values(".env")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'
}

page = requests.get('https://historyreborn.net/?module=item&action=view&id='+config['ITEM_ID'], headers=headers)
                    
soup = BeautifulSoup(page.text, 'html.parser')

tableStore = soup.find(id="nova-sale-table")

sendMessage = 'false'

for rows in tableStore.find_all('tr'):
    if("CASH" in rows.find_all('td')[5].text):
        if(int(rows.find('font').text.replace(',', '')) <= int(config['ITEM_PRECO'])):
            sendMessage = 'true'
            print(rows.find('font').text)
            print('-----------')

# if(sendMessage == 'true'):
#     subject = "History Reborn - Tá baratim"
#     body = "O produto X chegou no preço"
#     sender_email = config['SENDER_EMAIL']
#     recipient_email = config['RECIPIENT_EMAIL']
#     sender_password = config['GMAIL_TOKEN']
#     smtp_server = 'smtp.gmail.com'
#     smtp_port = 465

#     message = MIMEMultipart()
#     message['Subject'] = subject
#     message['From'] = sender_email
#     message['To'] = recipient_email
#     body_part = MIMEText(body)
#     message.attach(body_part)

#     with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
#         server.login(sender_email, sender_password)
#         server.sendmail(sender_email, recipient_email, message.as_string())
    
print('Finalizou :)')