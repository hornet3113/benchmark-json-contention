// init.js — colección de MongoDB (R-01, playbook.pdf §2, p.1).
//
// La ejecuta scripts/load_dataset.sh de forma EXPLÍCITA (ver docker/postgres/init.sql
// para el porqué). Se corre con: mongosh <base> --eval "$(cat init.js)"
//
// DESTRUCTIVO: borra la colección y su contenido.

db.orders.drop();
// Colección normal, sin sharding (mongod standalone), motor WiredTiger (R-01).
db.createCollection("orders");
print("init.js: colección 'orders' recreada en la base " + db.getName());
