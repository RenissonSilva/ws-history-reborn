import smtplib
import os
import cloudscraper
import mysql.connector
import traceback
import time
import re 
import requests # <--- NOVO: Necessário para o Telegram
import html  # <--- Adicione isso junto com os outros imports
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURAÇÕES GERAIS ---
load_dotenv()
MAX_EXECUTIONS = 2
WAIT_TIME_MINUTES = 1
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 465

# --- FUNÇÃO TELEGRAM ---
def sendTelegram(chat_id, message):
    token = os.getenv("TELEGRAM_TOKEN")
    if not token or not chat_id:
        print(" -> [Telegram] Token ou Chat ID ausente.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            print(f" -> [Telegram] Mensagem enviada para ID {chat_id}")
        else:
            print(f" -> [Telegram] Erro API: {response.text}")
    except Exception as e:
        print(f" -> [Telegram] Erro de conexão: {e}")

# --- FUNÇÃO EMAIL (Atualizada para aceitar destinatário) ---
def sendEmail(recipientEmail, subject, body):
    senderEmail = os.getenv("SENDER_EMAIL")
    senderPassword = os.getenv("GMAIL_TOKEN")

    if not senderEmail or not senderPassword:
        print("ERRO: Credenciais de email não configuradas no .env")
        return

    message = MIMEMultipart()
    message['Subject'] = subject
    message['From'] = senderEmail
    message['To'] = recipientEmail
    message['X-Priority'] = '1'
    message['X-MSMail-Priority'] = 'High'

    body_part = MIMEText(body, 'html')
    message.attach(body_part)

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(senderEmail, senderPassword)
            server.sendmail(senderEmail, recipientEmail, message.as_string())
            print(f" -> [Email] Enviado para {recipientEmail}")
    except Exception as e:
        print(f"ERRO ao enviar email: {e}")

def checkPrices():
    conexao = None
    cursor = None
    
    try:
        print("\n--- INICIANDO VERIFICAÇÃO ---")
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

        # Busca itens
        cursor.execute("SELECT * FROM items")
        itens_bd = cursor.fetchall()
            
        # Variáveis para montagem do EMAIL
        htmlListItens = "<h2>Lista de itens monitorados</h2>"
        bodyHtml = ""
        removeEmptyItems = []

        # Variável para montagem do TELEGRAM (Lista de textos curtos)
        telegramAlerts = [] 

        sendMessage = False
        page = cloudscraper.create_scraper()

        for item in itens_bd:
            itemId = str(item[2])
            targetRefinement = int(item[3]) if item[3] is not None else 0
            itemPriceTarget = int(item[4])
            targetCurrency = str(item[5]).strip() if len(item) > 5 and item[5] else "Zeny"

            removeEmptyItems.append(itemId)

            print(f"🔎 Analisando ID: {itemId} | Alvo: {targetCurrency} {itemPriceTarget} | Ref: +{targetRefinement}")

            url_item = f"{baseUrl}/?module=item&action=view&id={itemId}"
            scraper = page.get(url_item)
            time.sleep(1)

            soup = BeautifulSoup(scraper.content, "html.parser")

            # Nome do Item
            try:
                title_div = soup.find("div", {"class": "item-title-text"})
                if title_div:
                    for span in title_div.find_all("span"): span.decompose()
                    itemName = title_div.get_text().strip()
                else:
                    itemName = f"Item {itemId}"
            except:
                itemName = f"Item {itemId}"

            htmlListItens += f"<p><b>{itemName}</b> | Alvo: {itemPriceTarget} ({targetCurrency}) | Ref: +{targetRefinement}</p>"

            shops_section = soup.find("div", {"class": "shops-section"})
            if not shops_section: continue

            tableStore = shops_section.find("table", {"class": "shops-table"})
            if not tableStore or not tableStore.find("tbody"): continue

            # Cabeçalho temporário para Email
            tempHeader = f"""
                <h3 class='{itemId}'>
                    <a href='{url_item}'>{itemName}</a> <small>(Busca: {targetCurrency} / Ref +{targetRefinement})</small>
                </h3>
                <table class='{itemId}'>
                    <tr><th>Loja</th><th>Ref</th><th>Cartas</th><th>Valor</th><th>Qtd</th><th>Tipo</th></tr>
            """
            
            foundItemAlert = False
            itemRowsHtml = ""

            rows = tableStore.find("tbody").find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 5: continue

                try:
                    shop_div = cols[0].find("div", class_="shop-name")
                    storeName = shop_div.get_text().strip() if shop_div else "Desconhecido"

                    raw_refinement = cols[1].get_text().strip()
                    currentRefinement = int(raw_refinement.replace("+", "")) if "+" in raw_refinement or raw_refinement.isdigit() else 0
                    
                    cards = cols[2].get_text().strip()
                    
                    raw_price_text = cols[3].get_text().strip()
                    price_clean = re.sub(r'[^\d]', '', raw_price_text)
                    if not price_clean: continue
                    currentPrice = int(price_clean)

                    quantity = cols[4].get_text().strip()
                    raw_currency_type = cols[5].get_text().strip()
                    
                    # Filtros
                    if targetCurrency.strip().upper() != raw_currency_type.strip().upper(): continue
                    if currentRefinement < targetRefinement: continue

                    if currentPrice <= itemPriceTarget:
                        formattedPrice = "{:.2f}".format(float(currentPrice))
                        
                        comando = f"SELECT * FROM alerts WHERE item_id = '{itemId}' AND store_name = '{storeName}' AND price = '{formattedPrice}' AND date = '{todayDate}' AND currency = '{targetCurrency}'"
                        cursor.execute(comando)
                        
                        if cursor.rowcount == 0:
                            # --- ACHOU UMA OPORTUNIDADE ---
                            print(f"      ✅ OPORTUNIDADE: {storeName} | {raw_price_text}")
                            
                            foundItemAlert = True
                            sendMessage = True
                            if itemId in removeEmptyItems: removeEmptyItems.remove(itemId)

                            storeNameEscaped = storeName.replace("'", "")
                            insert_sql = f"""
                                INSERT INTO alerts (name, item_id, refinement, store_name, price, currency, date) 
                                VALUES ('{itemName}', '{itemId}', '{currentRefinement}', '{storeNameEscaped}', '{formattedPrice}', '{targetCurrency}', '{todayDate}')
                            """
                            cursor.execute(insert_sql)
                            conexao.commit()

                            # Adiciona linha no HTML do Email
                            itemRowsHtml += f"""<tr>
                                <td>{storeName}</td><td>+{currentRefinement}</td><td>{cards}</td>
                                <td>{raw_price_text}</td><td>{quantity}</td><td>{raw_currency_type}</td>
                            </tr>"""

                            safe_item_name = html.escape(itemName)
                            safe_store_name = html.escape(storeName)
                            safe_currency = html.escape(raw_currency_type)
                            # O preço e refino são numeros, nao precisa escapar, mas se forem strings, escape também.

                            # Adiciona texto na lista do Telegram (Texto Simples com variaveis limpas)
                            msg_tg = f"🔥 <b>{safe_item_name}</b>\n" \
                                        f"💰 <b>{raw_price_text}</b> ({safe_currency})\n" \
                                        f"🔨 Ref: +{currentRefinement}\n" \
                                        f"🏪 {safe_store_name}\n" \
                                        f"🔗 <a href='{url_item}'>Link</a>"
                            telegramAlerts.append(msg_tg)

                except Exception as row_error:
                    continue 

            if foundItemAlert:
                bodyHtml += tempHeader + itemRowsHtml + "</table>"

        # --- ROTINA DE NOTIFICAÇÃO (EMAIL VS TELEGRAM) ---
        if sendMessage:
            print("🚀 Preparando notificações...")

            # 1. Buscar usuários e suas preferências
            cursor.execute("SELECT email, preference, telegram_chat_id FROM users")
            users = cursor.fetchall() # Retorna lista de tuplas: (email, 'EMAIL'/'TELEGRAM', chat_id)

            # 2. Prepara o conteúdo do Email (Pesado, HTML Completo)
            final_html_email = None
            if any(u[1] == 'EMAIL' for u in users):
                html_template = f"""
                <html><head><style>
                    table {{font-family: arial, sans-serif; border-collapse: collapse; width: 100%;}}
                    td, th {{border: 1px solid #dddddd; text-align: left; padding: 8px;}}
                    tr:nth-child(even) {{background-color: #f2f2f2;}}
                    h2, h3 {{color: #8590ff;}} small {{color: #666; font-size: 0.8em;}}
                </style></head><body>{bodyHtml}<hr>{htmlListItens}</body></html>
                """
                soup_cleaner = BeautifulSoup(html_template, 'html.parser')
                # Remove tabelas vazias
                for itemId in removeEmptyItems:
                    for tag in soup_cleaner.find_all(["table", "h3"], {"class": itemId}):
                        tag.decompose()
                final_html_email = str(soup_cleaner)

            # 3. Prepara o conteúdo do Telegram (Leve, Texto)
            final_text_telegram = "🚨 <b>NOVAS OFERTAS ENCONTRADAS!</b> 🚨\n\n" + "\n\n----------------\n\n".join(telegramAlerts)

            # 4. Loop de Envio
            for user in users:
                # user_email = user[0]
                # user_pref = user[1]          # 'EMAIL' ou 'TELEGRAM'
                # user_chat_id = user[2]
                user_email = os.getenv("RECIPIENT_EMAIL")
                user_pref = 'TELEGRAM'
                user_chat_id = os.getenv("CHAT_ID")

                try:
                    if user_pref == 'EMAIL':
                        sendEmail(user_email, "Hero Ragnarok - OPORTUNIDADE!", final_html_email)
                    
                    elif user_pref == 'TELEGRAM':
                        if user_chat_id:
                            sendTelegram(user_chat_id, final_text_telegram)
                        else:
                            print(f" -> Usuário {user_email} quer Telegram mas não tem Chat ID.")
                    
                    else:
                        # Fallback: Se não definido ou estranho, manda email
                        sendEmail(user_email, "Hero Ragnarok - OPORTUNIDADE!", final_html_email)

                except Exception as e:
                    print(f"Erro ao notificar usuário {user_email}: {e}")

            return "Ciclo finalizado com alertas enviados."

        return "Ciclo finalizado sem novos alertas."

    except Exception as e:
        print(f"ERRO FATAL: {e}")
        traceback.print_exc()
        return "Erro na execução."
        
    finally:
        if cursor: cursor.close()
        if conexao and conexao.is_connected(): conexao.close()

if __name__ == "__main__":
    # ... (Bloco main igual ao anterior) ...
    print(f"Iniciando monitoramento: {MAX_EXECUTIONS} ciclos.")
    for i in range(MAX_EXECUTIONS):
        loop_start = datetime.now()
        print(f"🔄 Execução {i + 1} de {MAX_EXECUTIONS} - {loop_start.strftime('%H:%M:%S')}")
        checkPrices()
        if i < (MAX_EXECUTIONS - 1):
            time.sleep(WAIT_TIME_MINUTES * 60)