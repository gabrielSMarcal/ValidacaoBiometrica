-- Execute como administrador no phpMyAdmin, depois use aps_app na API.
-- Troque a senha abaixo E DB_PASSWORD no .env antes de executar.
CREATE DATABASE IF NOT EXISTS aps_facial CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'aps_app'@'localhost' IDENTIFIED BY 'troque_a_senha_no_sql_e_no_env';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, REFERENCES ON aps_facial.* TO 'aps_app'@'localhost';
-- O comando CREATE é necessário a python -m app.inicializar. Depois, opcionalmente:
-- REVOKE CREATE, REFERENCES ON aps_facial.* FROM 'aps_app'@'localhost';
-- Reexecutar este arquivo não troca senha de usuário que já existe.
