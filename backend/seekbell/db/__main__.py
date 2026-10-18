import argparse

from alembic import command

from seekbell.config import Settings
from seekbell.db.runtime import (
    create_database_engine,
    instance_lock,
    migrate,
    migration_config,
    schema_revision,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="SeekBell local database maintenance")
    parser.add_argument("action", choices=["upgrade", "current", "check"])
    args = parser.parse_args()
    settings = Settings()
    with instance_lock(settings.data_dir.resolve()):
        engine = create_database_engine(settings)
        try:
            if args.action == "upgrade":
                migrate(engine)
            elif args.action == "current":
                print(schema_revision(engine) or "uninitialized")
            else:
                config = migration_config()
                with engine.begin() as connection:
                    config.attributes["connection"] = connection
                    command.check(config)
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
