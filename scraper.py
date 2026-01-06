import smtplib
import os
import cloudscraper
import mysql.connector
import traceback
import time
import re 

from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

try:
    MAX_RETRIES = int(os.getenv("MAX_EXECUTIONS", 1))
    WAIT_MINUTES = int(os.getenv("EXECUTION_INTERVAL", 5))
except ValueError:
    print("Erro ao ler configurações de loop no .env. Usando padrão (1x).")
    MAX_RETRIES = 1
    WAIT_MINUTES = 5

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

    message['X-Priority'] = '1'
    message['X-MSMail-Priority'] = 'High'
    message['Importance'] = 'High'

    body_part = MIMEText(body, 'html')
    message.attach(body_part)

    with smtplib.SMTP_SSL(smtpServer, smtpPort) as server:
        server.login(senderEmail, senderPassword)
        server.sendmail(senderEmail, recipientEmail, message.as_string())

def checkPrices():
    try:
        baseUrl = os.getenv("BASE_URL")

        conexao = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DATABASE"),
            port=int(os.getenv("DB_PORT", 3306))
        )

        cursor = conexao.cursor(buffered=True)
        todayDate = datetime.today().strftime('%Y-%m-%d')

        cursor.execute("SELECT * FROM items")
        itens_bd = cursor.fetchall()
            
        htmlListItens = "<h2>Lista de itens monitorados</h2>"
        bodyHtml = ""
        sendMessage = False
        removeEmptyItems = []

        page = cloudscraper.create_scraper()

        for item in itens_bd:
            itemId = str(item[2])
            
            targetRefinement = item[3] 
            targetRefinement = int(targetRefinement) if targetRefinement is not None else 0

            itemPriceTarget = int(item[4]) 
            targetCurrency = item[5] if len(item) > 5 and item[5] else "Zeny"

            removeEmptyItems.append(itemId)

            print(f"Verificando ID: {itemId} | Meta: {targetCurrency} {itemPriceTarget} | Refino Mínimo: +{targetRefinement}")

            url_item = f"{baseUrl}/?module=item&action=view&id={itemId}"
            scraper = page.get(url_item)
            
            time.sleep(1) 

            soup = BeautifulSoup(scraper.content, "html.parser")

            try:
                title_div = soup.find("div", {"class": "item-title-text"})
                if title_div:
                    for span in title_div.find_all("span"):
                        span.decompose()
                    itemName = title_div.get_text().strip()
                else:
                    itemName = f"Item {itemId}"
            except:
                itemName = f"Item {itemId}"

            htmlListItens += f"<p><b>{itemName}</b> | Alvo: {itemPriceTarget} ({targetCurrency}) | Ref: +{targetRefinement}</p>"

            shops_section = soup.find("div", {"class": "shops-section"})
            
            if not shops_section:
                print(f" -> Sem lojas para {itemName}")
                continue

            tableStore = shops_section.find("table", {"class": "shops-table"})
            if not tableStore: continue
            
            tbody = tableStore.find("tbody")
            if not tbody: continue

            bodyHtml += f"""
                <h3 class='{itemId}'>
                    <a href='{url_item}'>{itemName}</a> <small>(Busca: {targetCurrency} / Ref +{targetRefinement})</small>
                </h3>
                <table class='{itemId}'>
                    <tr><th>Loja</th><th>Ref</th><th>Cartas</th><th>Valor</th><th>Qtd</th><th>Tipo</th></tr>
                """

            rows = tbody.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue

                try:
                    shop_div = cols[0].find("div", class_="shop-name")
                    storeName = shop_div.get_text().strip() if shop_div else "Desconhecido"

                    raw_refinement = cols[1].get_text().strip()
                    try:
                        currentRefinement = int(raw_refinement.replace("+", ""))
                    except:
                        currentRefinement = 0

                    cards = cols[2].get_text().strip()

                    raw_price_text = cols[3].get_text().strip()
                    price_clean = re.sub(r'[^\d]', '', raw_price_text)
                    if not price_clean: continue
                    currentPrice = int(price_clean)

                    quantity = cols[4].get_text().strip()
                    raw_currency_type = cols[5].get_text().strip()
                    
                    # --- FILTROS ---
                    if targetCurrency.upper() != raw_currency_type.upper(): continue
                    if currentRefinement < targetRefinement: continue

                    if currentPrice <= itemPriceTarget:
                        formattedPrice = "{:.2f}".format(float(currentPrice))
                        
                        comando = f"SELECT * FROM alerts WHERE item_id = '{itemId}' AND store_name = '{storeName}' AND price = '{formattedPrice}' AND date = '{todayDate}' AND currency = '{targetCurrency}';"
                        cursor.execute(comando)

                        if cursor.rowcount == 0:
                            if itemId in removeEmptyItems: removeEmptyItems.remove(itemId)
                            sendMessage = True
                            print(f"!!! ALERTA ATINGIDO !!! Item: {itemName} | Ref: +{currentRefinement} | Preço: {raw_price_text}")

                            storeNameEscaped = storeName.replace("'", "")
                            comando = f"""
                                INSERT INTO alerts (name, item_id, refinement, store_name, price, currency, date) 
                                VALUES ('{itemName}', '{itemId}', '{currentRefinement}', '{storeNameEscaped}', '{formattedPrice}', '{targetCurrency}', '{todayDate}')
                            """
                            cursor.execute(comando)
                            conexao.commit()

                            bodyHtml += f"""<tr>
                                <td>{storeName}</td>
                                <td>+{currentRefinement}</td>
                                <td>{cards}</td>
                                <td>{raw_price_text}</td>
                                <td>{quantity}</td>
                                <td>{raw_currency_type}</td>
                            </tr>"""
                
                except Exception as e:
                    print(f"Erro ao processar linha: {e}")
                    continue

            bodyHtml += """</table>"""

        html = """
            <html>
                <head>
                    <style>
                        table {font-family: arial, sans-serif; border-collapse: collapse; width: 100%;}
                        td, th {border: 1px solid #dddddd; text-align: left; padding: 8px;}
                        tr:nth-child(even) {background-color: #f2f2f2;}
                        h2, h3 {color: #8590ff;}
                        small {color: #666; font-size: 0.8em;}
                    </style>
                </head>
                <body>
                    """ + bodyHtml + """
                    <hr>
                    """ + htmlListItens + """
                </body>
            </html>
        """

        html_soup = BeautifulSoup(html, 'html.parser')
        
        for itemId in removeEmptyItems:
            for tag in html_soup.find_all("table", {"class": itemId}): tag.decompose()
            for tag in html_soup.find_all("h3", {"class": itemId}): tag.decompose()

        if sendMessage:
            subject = "Hero Ragnarok - OPORTUNIDADE ENCONTRADA!"
            body = str(html_soup)
            sendEmail(subject, body)
            return "Email enviado com sucesso!"

        cursor.close()
        conexao.close()
        return "Executado com sucesso (sem novos alertas)."

    except Exception as e:
        print(f"Ocorreu um erro fatal: {e}")
        traceback.print_exc()
        try:
            if 'conexao' in locals() and conexao.is_connected():
                cursor.close()
                conexao.close()
        except:
            pass
        return "Ocorreu um erro, verificar logs!"

if __name__ == "__main__":
    print(f"Configuração iniciada: {MAX_RETRIES} execuções.")
    
    for i in range(MAX_RETRIES):
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"🚀 Execução {i + 1} de {MAX_RETRIES} - Início: {current_time}")
        
        resultado = checkPrices()
        print(f"📝 Resultado: {resultado}")
        
        if i < (MAX_RETRIES - 1):
            next_run_seconds = WAIT_MINUTES * 60
            print(f"💤 Aguardando {WAIT_MINUTES} minutos para a próxima verificação...")
            print("-" * 50)
            time.sleep(next_run_seconds)
        else:
            print("-" * 50)
            print("🏁 Todas as verificações foram concluídas.")