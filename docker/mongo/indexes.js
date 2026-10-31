// indexes.js — índices de MongoDB, creados DESPUÉS de la carga (F3-c).
//
// R-02 (playbook.pdf §2): "índice simple en timestamp y order_id". Se leen como
// dos índices de un solo campo (A3.1), no uno compuesto. No son únicos (F3-b):
// el manual no lo pide; la unicidad de order_id la garantiza el generador y la
// comprueba G1.
//
// Ningún índice sobre payment.final_total (R-15).

db.orders.createIndex({ timestamp: 1 }, { name: "idx_orders_timestamp" });
db.orders.createIndex({ order_id: 1 }, { name: "idx_orders_order_id" });
print("indexes.js: " + JSON.stringify(db.orders.getIndexes().map(i => i.name)));
