import requests
import smtplib
import schedule
import time
import csv
import os
import cloudscraper

from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from dotenv import dotenv_values
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

def checkPrices():
    # Caminho para o arquivo CSV
    arquivo_csv = 'mail_history.csv'

    todayDate = datetime.today().strftime('%Y-%m-%d')

    currentHour = datetime.today().strftime('%H:%M')
    resetCsv = False

    if(currentHour == '00:00'):
        resetCsv = True
        
        with open(arquivo_csv, 'w', encoding='utf-8') as arquivo:
            # O conteúdo do arquivo é truncado, deixando-o vazio
            pass

    #   Itens que vão ser monitorados
    itens = {}
        
    # Pega id e preço de cada item do env
    contador = 1
    while os.environ.get('item_id_'+str(contador)) is not None:
        item_id = os.environ.get('item_id_'+str(contador))
        price_id = os.environ.get('price_id_'+str(contador))

        itens[item_id] = price_id

        contador += 1

    #   idItem: preçoItem
    # itens = {
    #     9288: 300000, # Ovo de Dragão da Serenidade
    #     6608: 30, # Mana coagulada
    #     600024: 60000, # Dragonic Slayer-LT [2] 
    #     27361: 2500, # Contaminated Wanderer Card
    #     480084: 80000, # Manto De Fafnir [1]
    #     490166: 9000, # Heroic Token (Dragon Knight) [1] 
    #     470115: 20000, # Snow Flower Boots [1]  
    # }

    bodyHtml = ""

    for itemId in itens:
        itemPrice = itens[itemId]

        page = cloudscraper.create_scraper()
        scraper = page.get('https://historyreborn.net/?module=item&action=view&id='+str(itemId))
                            
        soup = BeautifulSoup(scraper.content,"html.parser")
        tableStore = soup.find(id="nova-sale-table")

        sendMessage = 'false'

        itemName = soup.findAll('h2')[1].text

        #   Início da criação da tabela de um item
        bodyHtml += """
            <h2>""" + itemName + """</h2>

            <table>
                <tr>
                    <th>Loja</th>
                    <th>Refinamento</th>
                    <th>Cartas</th>
                    <th>Valor</th>
                    <th>Qtd</th>
                </tr>
            """

        for rows in tableStore.find_all('tr'):
            rowItem = ""
            if("CASH" in rows.find_all('td')[5].text):

                if(int(rows.find('font').text.replace(',', '')) <= int(itemPrice)):
                    storeName = rows.find_all('td')[0].text
                    refinement = rows.find_all('td')[1].text
                    cards = rows.find_all('td')[2].text
                    price = rows.find_all('td')[3].text
                    quantity = rows.find_all('td')[4].text

                    #   Adicionando valores em cada uma das células da tabela
                    if(storeName):
                        priceFormatado = int(rows.find('font').text.replace(',', ''))

                        # Linha que você deseja procurar
                        linha_especifica = [todayDate, str(itemId), str(priceFormatado)]

                        # Variável para indicar se a linha foi encontrada
                        linha_encontrada = False

                        # Procura se já foi enviado um email hoje com o alerta do item
                        with open(arquivo_csv, newline='', encoding='utf-8') as csvfile:
                            leitor = csv.reader(csvfile)
                            for linha in leitor:
                                # Comparando a linha atual com a linha específica
                                if linha == linha_especifica:
                                    linha_encontrada = True
                                    break

                        if(linha_encontrada == False):
                            sendMessage = 'true'

                            # Adiciona no arquivo csv e no html o item
                            with open('mail_history.csv', 'a') as f:
                                writer = csv.writer(f)
                                writer.writerow([todayDate, itemId, priceFormatado])

                            rowItem += """   <tr>
                                                <td>""" + storeName + """</td>
                                                <td>""" + refinement + """</td>
                                                <td>""" + cards + """</td>
                                                <td>""" + price + """</td>
                                                <td>""" + quantity + """</td>
                                            </tr>"""
                        bodyHtml += rowItem

        bodyHtml += """</table>"""


            
    #   Contrói HTML que vai ser enviado pelo email
    html = """
        <html>
            <head>
                <style>
                    table {
                        font-family: arial, sans-serif;
                        border-collapse: collapse;
                        width: 100%;
                    }

                    td, th {
                        border: 1px solid #dddddd;
                        text-align: left;
                        padding: 8px;
                        width: 200px;
                    }

                    tr:nth-child(even) {
                        background-color: #dddddd;
                    }
                </style>
            </head>
            <body>
                """ + bodyHtml + """
            </body>
        </html>
    """

    if(sendMessage == 'true' and resetCsv == False):
        subject = "History Reborn - Alerta atingido"
        body = html
        sender_email = os.environ.get("SENDER_EMAIL")
        recipient_email = os.environ.get("RECIPIENT_EMAIL")
        sender_password = os.environ.get("GMAIL_TOKEN")
        smtp_server = 'smtp.gmail.com'
        smtp_port = 465

        message = MIMEMultipart()
        message['Subject'] = subject
        message['From'] = sender_email
        message['To'] = recipient_email
        body_part = MIMEText(body, 'html')
        message.attach(body_part)

        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, message.as_string())

    return "Executado com sucesso!"

# if __name__ == "__main__":
#     scheduler = BlockingScheduler()
#     scheduler.add_job(checkPrices, 'interval', minutes=1)
#     print("Scheduler iniciado. Aguardando tarefas...")
#     scheduler.start()

checkPrices()