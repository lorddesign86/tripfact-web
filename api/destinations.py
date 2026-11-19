"""ASCII catch-all route accepts both decoded and percent-encoded city names."""
from api.catalog import handler as CatalogHandler
class handler(CatalogHandler):
    pass
