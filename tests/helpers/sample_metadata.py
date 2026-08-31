"""Minimal sample record metadata for importer client tests."""

sample_metadata_journal_article_pdf = {
    "access": {
        "files": "public",
        "record": "public",
        "status": "open",
    },
    "files": {"enabled": True},
    "metadata": {
        "title": "Sample Journal Article for Import Client Tests",
        "creators": [
            {
                "person_or_org": {
                    "type": "personal",
                    "name": "Doe, Jane",
                    "family_name": "Doe",
                    "given_name": "Jane",
                }
            }
        ],
        "resource_type": {"id": "publication-article"},
        "publication_date": "2020-01-01",
        "identifiers": [
            {"scheme": "import-recid", "identifier": "test-sample-001"},
        ],
    },
}
