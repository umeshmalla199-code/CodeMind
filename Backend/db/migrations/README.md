# Database migrations

CodeMind uses Alembic for versioned schema changes.  The application runs
`upgrade head` during startup, before seeding data.

For manual operations from the repository root:

```powershell
Backend\venv\Scripts\python.exe -m alembic upgrade head
Backend\venv\Scripts\python.exe -m alembic current
```

Create every future schema change as a new revision; do not add handwritten
`ALTER TABLE` statements to application startup.
