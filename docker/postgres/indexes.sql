-- indexes.sql — índices de PostgreSQL, creados DESPUÉS de la carga (F3-c).
--
-- R-04 (playbook.pdf §2): "PK en id; B-Tree sobre timestamp extraído del JSONB".
-- La PK ya la crea init.sql. Aquí va el B-Tree sobre el timestamp.
--
-- A3.2 (decidido): se indexa el timestamp extraído como TEXTO, sin cast, y Q2
-- no se modifica. No se exige que el planner lo use; si no lo usa, se reporta.
-- La prueba de qué variantes con cast son creables vive aparte, en
-- scripts/checks/a32_index_variants.sql.
--
-- Ningún índice sobre final_total (R-15): Q2 debe ordenar sin índice previo.

CREATE INDEX idx_orders_timestamp ON orders USING btree ((data->>'timestamp'));
