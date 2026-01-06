import smtplib
import os
import cloudscraper
import mysql.connector
import traceback
import time
import re # Importado para limpar o preço com regex

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

        # Executar a consulta SQL
        cursor.execute("SELECT * FROM items")
        itens_bd = cursor.fetchall()
            
        htmlListItens = "<h2>Lista de itens monitorados</h2>"
        bodyHtml = ""
        sendMessage = False
        removeEmptyItems = []

        for item in itens_bd:
            itemId = str(item[2])
            itemPriceTarget = int(item[4]) # Preço alvo do banco
            removeEmptyItems.append(itemId)

            print(f"Verificando Item ID: {itemId}...")

            page = cloudscraper.create_scraper()
            url_item = f"{baseUrl}/?module=item&action=view&id={itemId}"
            scraper = page.get(url_item)

            soup = BeautifulSoup(scraper.content, "html.parser")

            # --- 1. Extração do Nome do Item (Ajustado para o novo HTML) ---
            try:
                title_div = soup.find("div", {"class": "item-title-text"})
                if title_div:
                    # Remove o span do ID para pegar só o nome limpo
                    for span in title_div.find_all("span"):
                        span.decompose()
                    itemName = title_div.get_text().strip()
                else:
                    # Fallback caso mude algo
                    itemName = f"Item {itemId}"
            except:
                itemName = f"Item {itemId}"

            htmlListItens += f"<p><b>{itemName}</b> | Preço Alvo: {itemPriceTarget}</p>"

            # --- 2. Localização da Tabela de Lojas ---
            shops_section = soup.find("div", {"class": "shops-section"})
            
            # Se não tem seção de lojas ou tabela, pula
            if not shops_section:
                print(f"Sem seção de lojas para {itemName}")
                continue

            tableStore = shops_section.find("table", {"class": "shops-table"})
            if not tableStore:
                continue
            
            tbody = tableStore.find("tbody")
            if not tbody:
                continue

            # Início do HTML do email para este item
            bodyHtml += f"""
                <h3 class='{itemId}'>
                    <a href='{url_item}'>{itemName}</a>
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

            # --- 3. Iteração das Linhas (Ajustado para as colunas do HTML) ---
            # Estrutura do HTML fornecido:
            # 0: Loja (div.shop-name) | 1: Refino | 2: Cartas | 3: Preço | 4: Qtd | 5: Badge (RMT/ROPS/Zeny)
            
            rows = tbody.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                
                # Proteção: precisa ter as colunas esperadas
                if len(cols) < 5: 
                    continue

                try:
                    # -- Extração de Dados --
                    
                    # Nome da Loja
                    shop_div = cols[0].find("div", class_="shop-name")
                    storeName = shop_div.get_text().strip() if shop_div else "Desconhecido"

                    # Refinamento e Cartas
                    refinement = cols[1].get_text().strip()
                    cards = cols[2].get_text().strip()

                    # Preço (Coluna 3) - Limpeza pesada
                    raw_price_text = cols[3].get_text().strip()
                    # Remove 'c', 'z', 'RMT', virgulas, pontos e espaços
                    # Ex: "85,000c" -> "85000", "50 RMT" -> "50"
                    price_clean = re.sub(r'[^\d]', '', raw_price_text)
                    
                    if not price_clean: continue # Se não achou numero, pula
                    
                    currentPrice = int(price_clean)

                    # Quantidade
                    quantity = cols[4].get_text().strip()

                    # Tipo de Moeda (Coluna 5)
                    currency_type = cols[5].get_text().strip() # Ex: RMT, ROPS, ZENY

                    # -- Lógica de Alerta --
                    # Aqui você pode filtrar se quer verificar o preço independente da moeda (RMT vs Zeny)
                    # O código abaixo compara o número cru. Se itemPriceTarget for em Zeny e o cara vender em RMT (valor baixo), vai alertar.
                    
                    if currentPrice <= itemPriceTarget:
                        rowItem = ""
                        foundLine = False
                        formattedPrice = "{:.2f}".format(float(currentPrice))
                        
                        # Verifica se já alertou hoje
                        comando = f"SELECT * FROM alerts WHERE item_id = '{itemId}' AND store_name = '{storeName}' AND price = '{formattedPrice}' AND date = '{todayDate}';"
                        cursor.execute(comando)

                        if cursor.rowcount > 0:
                            foundLine = True
                        else:
                            if itemId in removeEmptyItems: removeEmptyItems.remove(itemId)
                        
                        if not foundLine:
                            sendMessage = True
                            print(f"ALERTA: {itemName} | Loja: {storeName} | Valor: {raw_price_text}")

                            # Insere no banco
                            # Escape simples para o nome da loja evitar erro de SQL com aspas
                            storeNameEscaped = storeName.replace("'", "")
                            comando = f"INSERT INTO alerts (name, item_id, refinement, store_name, price, date) VALUES ('{itemName}', '{itemId}', '{refinement}', '{storeNameEscaped}', '{formattedPrice}', '{todayDate}')"
                            cursor.execute(comando)
                            conexao.commit()

                            rowItem += f"""   <tr>
                                                <td>{storeName}</td>
                                                <td>{refinement}</td>
                                                <td>{cards}</td>
                                                <td>{raw_price_text}</td>
                                                <td>{quantity}</td>
                                                <td>{currency_type}</td>
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
        
        # Limpa tabelas vazias do HTML final
        for itemId in removeEmptyItems:
            for tag in html_soup.find_all("table", {"class": itemId}):
                tag.decompose()

            for tag in html_soup.find_all("h3", {"class": itemId}):
                tag.decompose()

        if sendMessage:
            subject = "Hero Ragnarok - Alerta de Preço!"
            body = str(html_soup)
            sendEmail(subject, body)
            return "Email enviado com sucesso!"

        cursor.close()
        conexao.close()
        return "Executado com sucesso (sem novos alertas)."

    except Exception as e:
        print(f"Ocorreu um erro fatal: {e}")
        traceback.print_exc()

        # Log de erro no email (opcional, mantendo sua lógica)
        try:
            if 'conexao' in locals() and conexao.is_connected():
                cursor = conexao.cursor(buffered=True)
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