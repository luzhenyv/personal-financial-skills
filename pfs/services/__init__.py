"""Service layer — business logic and data access for the PFS backend.

Routers delegate to service functions here; each service receives a
SQLAlchemy ``Session`` via FastAPI dependency injection.
"""
