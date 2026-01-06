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

        # Busca todos os itens para monitorar
        cursor.execute("SELECT * FROM items")
        itens_bd = cursor.fetchall()
            
        htmlListItens = "<h2>Lista de itens monitorados</h2>"
        bodyHtml = ""
        sendMessage = False
        removeEmptyItems = []

        for item in itens_bd:
            # Mapeamento das colunas baseado no seu Prisma Schema:
            # 0: id, 1: name, 2: item_id, 3: refinement, 4: price, 5: currency
            itemId = str(item[2])
            
            # Tratamento do Refinamento Alvo (Do Banco)
            targetRefinement = item[3] 
            if targetRefinement is None: 
                targetRefinement = 0
            else:
                targetRefinement = int(targetRefinement)

            # Tratamento do Preço Alvo
            itemPriceTarget = int(item[4]) 
            
            # Tratamento da Moeda Alvo (Do Banco) - Default Zeny se vier None
            targetCurrency = item[5] if len(item) > 5 and item[5] else "Zeny"

            removeEmptyItems.append(itemId)

            print(f"Verificando ID: {itemId} | Meta: {targetCurrency} {itemPriceTarget} | Refino Mínimo: +{targetRefinement}")

            page = cloudscraper.create_scraper()
            url_item = f"{baseUrl}/?module=item&action=view&id={itemId}"
            scraper = page.get(url_item)

            soup = BeautifulSoup(scraper.content, "html.parser")

            # --- 1. Extração do Nome do Item ---
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

            # --- 2. Localização da Tabela ---
            shops_section = soup.find("div", {"class": "shops-section"})
            
            if not shops_section:
                print(f" -> Sem lojas para {itemName}")
                continue

            tableStore = shops_section.find("table", {"class": "shops-table"})
            if not tableStore:
                continue
            
            tbody = tableStore.find("tbody")
            if not tbody:
                continue

            # Cabeçalho da tabela do email
            bodyHtml += f"""
                <h3 class='{itemId}'>
                    <a href='{url_item}'>{itemName}</a> <small>(Busca: {targetCurrency} / Ref +{targetRefinement})</small>
                </h3>

                <table class='{itemId}'>
                    <tr>
                        <th>Loja</th>
                        <th>Ref</th>
                        <th>Cartas</th>
                        <th>Valor</th>
                        <th>Qtd</th>
                        <th>Tipo</th>
                    </tr>
                """

            # --- 3. Iteração e Filtragem ---
            rows = tbody.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                
                if len(cols) < 5: 
                    continue

                try:
                    # -- Extração de Dados do HTML --
                    
                    # Nome da Loja
                    shop_div = cols[0].find("div", class_="shop-name")
                    storeName = shop_div.get_text().strip() if shop_div else "Desconhecido"

                    # Refinamento (HTML ex: "+7" ou "0")
                    raw_refinement = cols[1].get_text().strip()
                    try:
                        currentRefinement = int(raw_refinement.replace("+", ""))
                    except:
                        currentRefinement = 0

                    # Cartas
                    cards = cols[2].get_text().strip()

                    # Preço e Limpeza
                    raw_price_text = cols[3].get_text().strip()
                    price_clean = re.sub(r'[^\d]', '', raw_price_text)
                    if not price_clean: continue
                    currentPrice = int(price_clean)

                    # Quantidade
                    quantity = cols[4].get_text().strip()

                    # Moeda (HTML ex: "ROPS", "RMT", "ZENY")
                    raw_currency_type = cols[5].get_text().strip()
                    print('raw_currency_type', raw_currency_type)
                    
                    # --- FILTROS ---

                    # 1. Filtro de Moeda
                    # Compara ignorando maiusculas/minusculas (ex: "Zeny" == "ZENY")
                    if targetCurrency.upper() != raw_currency_type.upper():
                        # print(f"Ignorado: Moeda errada ({raw_currency_type} vs {targetCurrency})")
                        continue

                    # 2. Filtro de Refinamento
                    # Verifica se o refino da loja é MENOR que o alvo. Se for, ignora.
                    if currentRefinement < targetRefinement:
                        # print(f"Ignorado: Refino baixo (+{currentRefinement} vs +{targetRefinement})")
                        continue

                    # 3. Filtro de Preço
                    # Verifica se está barato o suficiente
                    if currentPrice <= itemPriceTarget:
                        rowItem = ""
                        foundLine = False
                        formattedPrice = "{:.2f}".format(float(currentPrice))
                        
                        # Verifica se já alertou hoje (compara também a Moeda no banco se possível, ou assume pela loja/preço)
                        # Nota: Adicionei currency na verificação para garantir
                        comando = f"SELECT * FROM alerts WHERE item_id = '{itemId}' AND store_name = '{storeName}' AND price = '{formattedPrice}' AND date = '{todayDate}' AND currency = '{targetCurrency}';"
                        cursor.execute(comando)

                        if cursor.rowcount > 0:
                            foundLine = True
                        else:
                            if itemId in removeEmptyItems: removeEmptyItems.remove(itemId)
                        
                        if not foundLine:
                            sendMessage = True
                            print(f"!!! ALERTA ATINGIDO !!! Item: {itemName} | Ref: +{currentRefinement} | Preço: {raw_price_text}")

                            # Insere no banco (AGORA COM CURRENCY)
                            storeNameEscaped = storeName.replace("'", "")
                            
                            # Query atualizada para incluir currency
                            comando = f"""
                                INSERT INTO alerts (name, item_id, refinement, store_name, price, currency, date) 
                                VALUES ('{itemName}', '{itemId}', '{currentRefinement}', '{storeNameEscaped}', '{formattedPrice}', '{targetCurrency}', '{todayDate}')
                            """
                            cursor.execute(comando)
                            conexao.commit()

                            rowItem += f"""   <tr>
                                                <td>{storeName}</td>
                                                <td>+{currentRefinement}</td>
                                                <td>{cards}</td>
                                                <td>{raw_price_text}</td>
                                                <td>{quantity}</td>
                                                <td>{raw_currency_type}</td>
                                            </tr>"""
                            
                            bodyHtml += rowItem
                
                except Exception as e:
                    print(f"Erro ao processar linha: {e}")
                    continue

            bodyHtml += """</table>"""

        #   Constrói HTML que vai ser enviado pelo email
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
                        }

                        tr:nth-child(even) {
                            background-color: #f2f2f2;
                        }

                        h2, h3 {
                            color: #8590ff;
                        }
                        small {
                            color: #666;
                            font-size: 0.8em;
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

        html_soup = BeautifulSoup(html, 'html.parser')
        
        # Limpa tabelas vazias
        for itemId in removeEmptyItems:
            for tag in html_soup.find_all("table", {"class": itemId}):
                tag.decompose()

            for tag in html_soup.find_all("h3", {"class": itemId}):
                tag.decompose()

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
                cursor = conexao.cursor(buffered=True)
                # Verifica tabela de erros (log simples)
                comando = f"SELECT * FROM error_emails WHERE date = '{todayDate}';"
                cursor.execute(comando)

                if(cursor.rowcount == 0):
                    subject = "ERRO - O sistema de alertas está com erro"
                    body =  f"Erro: {str(e)}"
                    sendEmail(subject, body)

                    comando = f"INSERT INTO error_emails (date) VALUES ('{todayDate}')"
                    cursor.execute(comando)
                    conexao.commit()
                cursor.close()
                conexao.close()
        except:
            pass

        return "Ocorreu um erro, verificar logs!"

if __name__ == "__main__":
    for i in range(4):
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"Execução {i + 1} de 5 - Horário: {current_time}")
        checkPrices()
        current_time_final = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"Terminou {i + 1} de 5 - Horário: {current_time_final}")