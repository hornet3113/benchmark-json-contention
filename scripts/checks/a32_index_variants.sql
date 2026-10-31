-- a32_index_variants.sql — ¿qué variante de índice sobre el timestamp es creable? (SPEC A3.2)
--
-- NO es parte del esquema. El índice decidido (A3.2, texto sin cast) lo crea
-- docker/postgres/indexes.sql. Esto solo PRUEBA las variantes con cast y
-- archiva la respuesta del servidor como evidencia. Todo índice de prueba se
-- borra al final.
--
-- Se ejecuta SIN ON_ERROR_STOP: un CREATE INDEX rechazado es un resultado, no
-- un fallo del script. Requiere la tabla orders cargada.

\echo '== 1. Casts texto -> timestamp/timestamptz según pg_cast (consulta de SPEC A3.2)'
\echo '   castmethod: f = función, i = conversión por I/O (funciones de entrada del tipo), b = binaria'
SELECT c.castsource::regtype AS origen, c.casttarget::regtype AS destino, c.castmethod,
       p.proname AS funcion, p.provolatile AS volatilidad
FROM pg_cast c LEFT JOIN pg_proc p ON p.oid = c.castfunc
WHERE c.castsource = 'text'::regtype
  AND c.casttarget IN ('timestamp'::regtype, 'timestamptz'::regtype);

\echo '== 2. Funciones de entrada de los tipos (las que usa una conversión por I/O)'
\echo '   provolatile: i = IMMUTABLE, s = STABLE, v = VOLATILE. Un índice exige IMMUTABLE.'
SELECT t.typname AS tipo, p.proname AS funcion_entrada, p.provolatile AS volatilidad
FROM pg_type t JOIN pg_proc p ON p.oid = t.typinput
WHERE t.typname IN ('timestamp', 'timestamptz', 'text')
ORDER BY t.typname;

\echo '== 3. Intento de crear cada variante'
\echo '-- 3a. texto sin cast (la decidida en A3.2)'
CREATE INDEX a32_test_text ON orders ((data->>'timestamp'));
\echo '-- 3b. cast a timestamp (sin zona)'
CREATE INDEX a32_test_ts ON orders (((data->>'timestamp')::timestamp));
\echo '-- 3c. cast a timestamptz (el que usa Q2)'
CREATE INDEX a32_test_tstz ON orders (((data->>'timestamp')::timestamptz));

\echo '== 4. Índices de prueba que llegaron a existir'
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename = 'orders' AND indexname LIKE 'a32_test_%' ORDER BY indexname;

\echo '== 5. Limpieza: se borran todos los índices de prueba'
DROP INDEX IF EXISTS a32_test_text;
DROP INDEX IF EXISTS a32_test_ts;
DROP INDEX IF EXISTS a32_test_tstz;
SELECT count(*) AS indices_de_prueba_restantes FROM pg_indexes
WHERE tablename = 'orders' AND indexname LIKE 'a32_test_%';
