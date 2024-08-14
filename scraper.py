import smtplib
import os
import cloudscraper
import mysql.connector

from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def sendEmail(subject, body):
        senderEmail = os.getenv("SENDER_EMAIL")
        recipientEmail = os.getenv("RECIPIENT_EMAIL")
        senderPassword = os.getenv("GMAIL_TOKEN")
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

def checkPrices():
    try:
        conexao = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DATABASE"),
        )

        cursor = conexao.cursor(buffered=True)

        todayDate = datetime.today().strftime('%Y-%m-%d')

        #   Itens que vão ser monitorados
        itens = {}
            
        # Pega id e preço de cada item do env
        count = 1
        while os.getenv('ITEM_ID_'+str(count)) is not None:
            item_id = os.getenv('ITEM_ID_'+str(count))
            price_id = os.getenv('PRICE_ID_'+str(count))

            itens[item_id] = price_id

            count += 1
            
        htmlListItens = "<h2>Lista de itens monitorados</h2>"

        bodyHtml = ""

        sendMessage = False
        removeEmptyItems = []

        for itemId in itens:
            itemPrice = itens[itemId]
            removeEmptyItems.append(itemId)

            page = cloudscraper.create_scraper()
            scraper = page.get('https://historyreborn.net/?module=item&action=view&id='+str(itemId))
                                
            soup = BeautifulSoup(scraper.content,"html.parser")
            tableStore = soup.find(id="nova-sale-table")

            itemName = soup.findAll('h2')[1].text

            htmlListItens += f"<p><b>{itemName}</b> | Preço: {itens[itemId]}</p>"

            #   Início da criação da tabela de um item
            bodyHtml += """
                <h3 class='"""+itemId+"""'>""" + itemName + """</h3>

                <table class='"""+itemId+"""'>
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
                        storeName = (rows.find_all('td')[0].text).strip()
                        refinement = (rows.find_all('td')[1].text).strip()
                        cards = (rows.find_all('td')[2].text).strip()
                        price = (rows.find_all('td')[3].text).replace("c", "").replace(",", "").strip()
                        quantity = (rows.find_all('td')[4].text).strip()

                        #   Adicionando valores em cada uma das células da tabela
                        if(storeName):
                            # Variável para indicar se a linha foi encontrada
                            foundLine = False
                            # Procura se já foi enviado um email hoje com o alerta do item
                            formattedPrice = "{:.2f}".format(float(price))
                            comando = f"SELECT * FROM alerts WHERE item_id = '{itemId}' AND store_name = '{storeName}' AND price = '{formattedPrice}' AND date = '{todayDate}';"
                            cursor.execute(comando)

                            if(cursor.rowcount > 0):
                                foundLine = True
                            else:
                                if itemId in removeEmptyItems: removeEmptyItems.remove(itemId)
                            

                            if(foundLine == False):
                                #   Início da criação da tabela de um item
                                sendMessage = True

                                # Adiciona no banco o item
                                comando = f"INSERT INTO alerts (name, item_id, refinement, store_name, price, date) VALUES ('{itemName}', '{itemId}', '{refinement}', '{storeName}', '{formattedPrice}', '{todayDate}')"
                                cursor.execute(comando)
                                conexao.commit()

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
                    """ + bodyHtml + """
                    <hr>
                    """ + htmlListItens + """
                </body>
            </html>
        """

        html = BeautifulSoup(html, 'html.parser')
        # soup.find_all('table')
        
        for itemId in removeEmptyItems:
            for tag in html.find_all("table", {"class": itemId}):
                tag.decompose()

            for tag in html.find_all("h3", {"class": itemId}):
                tag.decompose()

        if(sendMessage == True):
            subject = "History Reborn - Alerta atingido"
            body = html
            sendEmail(subject, body)

        cursor.close()
        conexao.close()
        return "Executado com sucesso!"
    except:
        comando = f"SELECT * FROM error_emails WHERE date = '{todayDate}';"
        cursor.execute(comando)

        if(cursor.rowcount == 0):
            subject = "ERRO - O sistema de alertas está com erro"
            body =  """
                        Verificar com o seguinte comando qual erro está acontecendo
                        <br>
                        heroku logs --app ws-history-reborn
                    """
            sendEmail(subject, body)

            comando = f"INSERT INTO error_emails (date) VALUES ('{todayDate}')"
            cursor.execute(comando)
            conexao.commit()

        return "Ocorreu um erro, verificar nos logs do Heroku!"
        
    

# if __name__ == "__main__":
#     scheduler = BlockingScheduler()
#     scheduler.add_job(checkPrices, 'interval', minutes=1)
#     print("Scheduler iniciado. Aguardando tarefas...")
#     scheduler.start()

checkPrices()