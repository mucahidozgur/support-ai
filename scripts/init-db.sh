#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE support_test OWNER $POSTGRES_USER;
    \c support_test
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
