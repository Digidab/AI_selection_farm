# db

Database schema, migrations, and SQL definitions.

The actual PostgreSQL data directory is not committed to Git — see `postgres_volume/` (bind mount,
git-ignored).

Full schema design, versioning strategy, and the "database vs. files" ownership rules are documented
in `readmy_info/selection_farm_database_guide.md`.
