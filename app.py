from flask import Flask
from scraper import checkPrices

app = Flask(__name__)

@app.route('/')
def index():
    return 'Home'
    # return checkPrices()

if __name__ == '__main__':
    # Executar no modo de desenvolvimento
    app.run()