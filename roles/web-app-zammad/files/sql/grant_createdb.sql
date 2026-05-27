-- Grant CREATEDB to the Zammad PostgreSQL role.
-- Zammad's init script unconditionally runs `rake db:create` even when the
-- database already exists; without CREATEDB the call fails with
-- `PG::InsufficientPrivilege: permission denied to create database`.
ALTER ROLE %(role_name)s WITH CREATEDB;
