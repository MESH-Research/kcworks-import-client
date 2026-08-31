"""KCWorks import client.

Library API for importing works via the KCWorks import API and for
orchestrating multi-collection imports from a manifest file.

Example::

    from kcworks_import_client import ImportClient, MultiCollectionImporter

    client = ImportClient(api_key="...")
    result = client.import_works(
        "my-collection",
        metadata=[{"metadata": {"title": "Example"}}],
        files=["paper.pdf"],
    )

    importer = MultiCollectionImporter(api_key="...")
    multi = importer.run_manifest("manifest.json", assign_parents=True)
"""

from .api_importer import import_works
from .client import ImportClient
from .exceptions import (
    CommunityError,
    ImportAPIError,
    ImportRequestError,
    KCWorksImportError,
    ManifestError,
)
from .multi_client import MultiCollectionImporter, load_manifest
from .results import ImportResult, MultiCollectionImportResult

__all__ = [
    "CommunityError",
    "ImportAPIError",
    "ImportClient",
    "ImportRequestError",
    "ImportResult",
    "KCWorksImportError",
    "ManifestError",
    "MultiCollectionImportResult",
    "MultiCollectionImporter",
    "import_works",
    "load_manifest",
]
__version__ = "0.1.0"
