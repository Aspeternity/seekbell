from alembic import context
from seekbell.db.models import Base

# The application supplies its configured connection after acquiring the instance lock.
# No second independently configured database URL or automatic create_all fallback.
connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
