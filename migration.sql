CREATE DATABASE ws_history_reborn;
USE ws_history_reborn;

CREATE TABLE alerts (
    alert_id int not null auto_increment,
    name varchar(255) not null,
    item_id int not null,
    refinement int,
    store_name varchar(255) not null,
    price decimal(12,2) not null,
    date date not null,
    primary key (alert_id)
)

CREATE TABLE items (
    id int not null auto_increment,
    name varchar(255) not null,
    item_id int not null,
    refinement int,
    price decimal(12,2) not null,
    primary key (id)
)

CREATE TABLE error_emails (
    id int not null auto_increment,
    date date NOT NULL,
	primary key (id)
);

INSERT INTO alerts (name, item_id, refinement, store_name, price, date) VALUES ('Mana coagulada', 6608, null, 'Apenas um teste', 105.20, '2024-08-07')

SELECT * FROM alerts WHERE item_id = '6608' AND store_name = 'Apenas um teste' AND date = '2024-08-07' AND price = 105.20;