import smtplib
import csv
import os
import cloudscraper

from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def checkPrices():
    # Caminho para o arquivo CSV
    csvFile = 'mail_history.csv'

    todayDate = datetime.today().strftime('%Y-%m-%d')

    currentHour = datetime.today().strftime('%H:%M')
    resetCsv = False

    if(currentHour == '00:00'):
        resetCsv = True
        
        with open(csvFile, 'w', encoding='utf-8') as arquivo:
            # O conteúdo do arquivo é truncado, deixando-o vazio
            pass

    #   Itens que vão ser monitorados
    itens = {}
        
    # Pega id e preço de cada item do env
    count = 1
    while os.environ.get('item_id_'+str(count)) is not None:
        item_id = os.environ.get('item_id_'+str(count))
        price_id = os.environ.get('price_id_'+str(count))

        itens[item_id] = price_id

        count += 1
        
    htmlListItens = "<h2>Lista de itens monitorados</h2>"

    bodyHtml = ""

    sendMessage = False

    for itemId in itens:
        itemPrice = itens[itemId]

        page = cloudscraper.create_scraper()
        scraper = page.get('https://historyreborn.net/?module=item&action=view&id='+str(itemId))
                            
        soup = BeautifulSoup(scraper.content,"html.parser")
        tableStore = soup.find(id="nova-sale-table")

        itemName = soup.findAll('h2')[1].text

        htmlListItens += f"<p><b>{itemName}</b> | Preço: {itens[itemId]}</p>"

        #   Início da criação da tabela de um item
        bodyHtml += """
            <h3>""" + itemName + """</h3>

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
                        formattedPrice = int(rows.find('font').text.replace(',', ''))

                        # Linha que você deseja procurar
                        specificLine = [todayDate, str(itemId), str(formattedPrice)]

                        # Variável para indicar se a linha foi encontrada
                        foundLine = False

                        # Procura se já foi enviado um email hoje com o alerta do item
                        with open(csvFile, newline='', encoding='utf-8') as csvfile:
                            leitor = csv.reader(csvfile)
                            for linha in leitor:
                                # Comparando a linha atual com a linha específica
                                if linha == specificLine:
                                    foundLine = True
                                    break

                        if(foundLine == False):
                            sendMessage = True

                            # Adiciona no arquivo csv e no html o item
                            with open('mail_history.csv', 'a') as f:
                                writer = csv.writer(f)
                                writer.writerow([todayDate, itemId, formattedPrice])

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
                        background-color: #b4b4b4;
                    }

                    h2, h3 {
                        color: #8590ff;
                    }
                </style>
            </head>
            <body>
                """ + htmlListItens + """
                <hr>
                """ + bodyHtml + """
            </body>
        </html>
    """

    if(sendMessage == True and resetCsv == False):
        subject = "History Reborn - Alerta atingido"
        body = html
        senderEmail = os.environ.get("SENDER_EMAIL")
        recipientEmail = os.environ.get("RECIPIENT_EMAIL")
        senderPassword = os.environ.get("GMAIL_TOKEN")
        smtpServer = 'smtp.gmail.com'
        smtpPort = 465

        message = MIMEMultipart()
        message['Subject'] = subject
        message['From'] = senderEmail
        message['To'] = recipientEmail
        body_part = MIMEText(body, 'html')
        message.attach(body_part)

        with smtplib.SMTP_SSL(smtpServer, smtpPort) as server:
            server.login(senderEmail, senderPassword)
            server.sendmail(senderEmail, recipientEmail, message.as_string())

    return "Executado com sucesso!"

# if __name__ == "__main__":
#     scheduler = BlockingScheduler()
#     scheduler.add_job(checkPrices, 'interval', minutes=1)
#     print("Scheduler iniciado. Aguardando tarefas...")
#     scheduler.start()

checkPrices()