-- init.sql — tabla de PostgreSQL (R-03, playbook.pdf §2, p.1).
--
-- La ejecuta scripts/load_dataset.sh de forma EXPLÍCITA, no la imagen desde
-- docker-entrypoint-initdb.d: la imagen solo corre esos scripts con el volumen
-- vacío, y el volumen se inicializó en F1. Ahí no fallaría: simplemente no
-- se ejecutaría (docs/F3_CARGA.md, problema 2).
--
-- DESTRUCTIVO: borra la tabla y su contenido. Por eso solo se llama desde la carga.

DROP TABLE IF EXISTS orders_staging;
DROP TABLE IF EXISTS orders;

-- Literal del manual: sin NOT NULL ni restricciones adicionales (F3-d).
CREATE TABLE orders (id UUID PRIMARY KEY, data JSONB);

-- Tabla intermedia para COPY: una línea JSONL por fila. El id se obtiene
-- después del propio documento, así id = order_id por construcción (SPEC §2).
-- UNLOGGED: es temporal y se borra al terminar la carga.
CREATE UNLOGGED TABLE orders_staging (doc JSONB);
