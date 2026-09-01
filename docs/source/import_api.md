# Streamlined Import API

This chapter documents the KCWorks **HTTP import API** that this package calls.
It is adapted from the KCWorks instance documentation so client users have the
full narrative without leaving this package.

In order to streamline the process of uploading works to KCWorks, particularly for works intended for publication in a collection, KCWorks provides a streamlined import API. This API allows clients to upload a work and its files in a single step, without the need to create a draft record, initialize file uploads, commit file uploads, or submit a review request.

Why is this API needed? The InvenioRDM REST API can be fragile and difficult to use, particularly for clients who are not familiar with the system. The creation and acceptance of a review request is redundant where collection administrators are uploading works for a collection they administer. The file upload steps are also not truly stateless, introducing the possibility of a file upload being interrupted and left incomplete, even if the upload of the file's content was successful.

```{note}
This package (`kcworks-import-client`) simplifies using the import API (library
classes and CLI). The single-collection importer handles authentication, file
uploads, and response formatting automatically. See
{ref}`the single-collection importer <kcworks-api-importer-script>` and
{ref}`the multi-collection importer <kcworks-multi-collection-importer-script>`.
```

## Who can use the import API?
The import API is available to authorized organizations who have obtained an OAuth token for API operations. The import API places the works directly in a collection, without passing through the review process. So, the user to whom the token is issued must have sufficient permissions to publish directly in the collection. The exact role required depends on the collection's review policy:

- _If the review policy allows managers and curators to skip the review process_, the user of the import API must have one of the roles "manager," "curator," or "owner" in the collection.
- _If the review policy requires all submissions to be reviewed_, the user of the import API must have the "owner" role in the collection.

## The import request
### Request
```http
POST https://works.hcommons.org/api/import/<my-collection-id> HTTP/1.1
```

### Required headers
```http
Content-Type: multipart/form-data
Accept: application/json
Authorization: Bearer <your-api-key>
```

### Request url path parameters
Only one URL path parameter is required:

| Name         | Required | Type     | Description                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ------------ | -------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `collection` | yes      | `string` | The ID (either the url slug or the UUID) of the collection to which the work should be published. The work will be submitted to the collection immediately after import. If the collection requires review, and the `review_required` parameter is set to "true", the work will be placed in the collection's review queue. Otherwise, if the uploader has sufficient permissions for the collection, the review process will be bypassed. |

### Request body
This request must be made with a `multipart/form-data` request. The request body must include parts with following names:

| Name                   | Required | Content Type               | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ---------------------- | -------- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `files`                | yes      | `application/octet-stream` | The (binary) file content to be uploaded. If multiple files are being uploaded, a body part with this same name ("files") must be provided for each file. If more than three or four files are being uploaded, it is recommended to provide a single zip archive containing all of the files. The files will be assigned to the appropriate work based on filename, so where multiple files are provided these file names **must be unique**. If a zip archive is provided, the files must be contained in a single compressed folder with no subfolders. |
| `metadata`             | yes      | `application/json`         | An array of JSON metadata objects, each of which will be used to create a new work. Each must conform to the KCWorks implementation of the InvenioRDM metadata schema described [here](https://mesh-research.github.io/knowledge-commons-works/reference/metadata.html). In addition, an array of owners for the work may optionally be provided by adding a `parent.access.owned_by` property to each metadata object. Note that if no owners are provided, the work will be created with the organizational account that issued the OAuth token as the owner.               |
| `review_required`      | no       | `text/plain`               | A string representation of a boolean (either "true" or "false") indicating whether the work should be reviewed before publication. This setting is only relevant if the work is intended for publication in a collection that requires review. It will override the collection's usual review policy, since the work is being uploaded by a collection administrator. (Default: "true")                                                                                                                                                                   |
| `strict_validation`    | no       | `text/plain`               | A string representation of a boolean (either "true" or "false") indicating whether the import request should be rejected if any validation errors are encountered. If this value is "false", the imported work will be created in KCWorks even if some of the provided metadata does not conform to the KCWorks metadata schema, provided these are not required fields. If this value is "true", the import request will be rejected if any validation errors are encountered. (Default: "true")                                                         |
| `all_or_none`          | no       | `text/plain`               | A string representation of a boolean (either "true" or "false") indicating whether the entire import request should be rejected if any of the works fail to be created (whether for validation errors, upload errors, or other reasons). If this value is "false", the import request will be accepted even if some of the works cannot be created. The response in this case will include a list of works that were successfully created and a list of errors for the works that failed to be created. (Default: "true")                                 |
| `notify_record_owners` | no       | `text/plain`               | A string representation of a boolean (either "true" or "false") indicating whether the owners of the work should be notified by email of the work's creation. (Default: `"false"`)                                                                                                                                                                                                                                                                                                                                                                       |
| `id_scheme`            | no       | `text/plain`               | Identifier scheme used to match existing works for idempotent re-import (looked up in each work's `metadata.identifiers`). Default: `import-recid`. The scheme must already be defined in KCWorks (`RDM_RECORDS_IDENTIFIERS_SCHEMES`), or arranged with the KCWorks team for addition before import. Built-in import-oriented schemes include `import-recid` and `neh-recid`.                                                                                                                                                                         |
| `alternate_id_scheme`  | no       | `text/plain`               | Optional secondary identifier scheme checked after `id_scheme` when looking up existing works. Same constraint as `id_scheme`. (Default: empty / unused)                                                                                                                                                                                                                                                                                                                                                                                                |
| `no_updates`           | no       | `text/plain`               | When `"true"`, refuse to change an existing matched work if its **metadata** differs from the import payload (soft skip; file handling is not reached in that case). When `"false"` (default), differing metadata is applied to the existing draft/record, and files are reconciled as described below under {ref}`import-existing-record-files`. Matching uses DOI / `id_scheme` so identical re-imports do not create duplicates. |

### Identifying the owners of the work
The array of owners, if provided in a metadata object's `parent.access.owned_by` property, must include at least the full name and email address of the users to be added as owners of the work. If the user already has a Knowledge Commons account, their username should also be provided. Additional identifiers (e.g., ORCID) may be provided as well to help avoid duplicate accounts, since a KCWorks account will be created for each user if they do not already have one.

| key           | required | type     | description                                                                                                                                                                                                                                                                                                                                                                                                           |
| ------------- | -------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `full_name`   | yes      | `string` | The full name of the user.                                                                                                                                                                                                                                                                                                                                                                                            |
| `email`       | yes      | `string` | The email address of the user.                                                                                                                                                                                                                                                                                                                                                                                        |
| `identifiers` | no       | `array`  | An array of identifiers for the user. Any identifier schemes supported by KCWorks will be accepted. If the user already has a KCWorks account, the `kc_username` scheme should be used and the user's username provided as the identifier. If you wish to provide an ORCID, it is recommended to use the `orcid` scheme. Identifiers for external organizations should be provided using the `import_user_id` scheme. |

The resulting `owners` list should be shaped like this:

```json
[
  {
    "full_name": "John Doe",
    "email": "john.doe@example.com",
    "identifiers": [
      {
        "identifier": "0000-0000-0000-0000",
        "scheme": "orcid"
      },
      {
        "identifier": "jdoe",
        "scheme": "kc_username"
      },
      {
        "identifier": "1234567890",
        "scheme": "import_user_id"
      }
    ]
  }
]
```

Note that it is _not_ assumed that the creators of a work should be the work's owners. The creators will only be added as owners if each of them is listed in the `access.owned_by` property of the work's metadata object.

> Note, too, that only the first member of the owners array will technically be assigned as the work's owner in KCWorks. The other owners will be assigned access grants to the work with "manage" permissions.

### KC accounts for work owners
KCWorks will create an internal KCWorks account for each work owner who does not already have an account on Knowledge Commons. Note that this _does not_ create a full Knowledge Commons account. The owner will still need to visit Knowledge Commons to create an account through the usual registration process. When they do so, their KCWorks account will be linked to their Knowledge Commons account and they will be able to manage and edit their uploaded works.

> It is vital that the owner provide an identifier when they create their Knowledge Commons account that matches an identifier provided for them in the `owned_by` property of the work's metadata object. This allows KCWorks to link the owner's KCWorks account to their Knowledge Commons account after they register. The connecting identifier may be
>
> - the same primary email address
> - the same ORCID identifier

If an owner does not already belong to the collection to which the records are being imported, that owner will also be added to the collection's membership with the "reader" role. The allows them access to any records restricted to the collection's membership, but does not afford them any additional permissions. What it does mean is that collection managers will be able to see all of the work owners in the list of collection members on the collection's landing page.

### Email notifications for work owners
When a work is imported into a collection, the work owners will receive an email notification only if the `notify_record_owners` parameter is set to `"true"`. (The default is `"false"`.) This email will include a link to the work's landing page on KCWorks. The email subject line and the email template used for this notification are configurable on a collection-by-collection basis. Authorized organizations should discuss the desired content with the KCWorks team.

For KCWorks developers: The configuration for this email is found in the config variable `RECORD_IMPORTER_COMMUNITIES` in the KCWorks instance's `invenio.cfg` file. This is a dictionary whose keys are the collection slugs and whose values are dictionaries with the following keys:

- `email_subject_import`: The subject line for the email notification.
- `email_template_import`: The name of the Jinja2 template file to use for the email notification. These templates must be located in the `templates/security/email` directory. One template file with an `.html` extension and one with a `.txt` extension are required, with identical names apart from the extension. The name provided in the `email_template_import` key should be the filename without the `.html` or `.txt` extension.

The template will receive the following variables:

- `record`: A dictionary containing the metadata for the imported work.
- `community_page_url`: The URL of the collection's landing page on KCWorks.
- `kc_registration_link`: The URL of the Knowledge Commons registration page.
- `user`: The KCWorks User object for the user being notified.

### Identifying the work for import
It is crucial that each work to be imported is assigned a unique identifier. This may be an identifier used internally by the importing organization, it may be a universally unique string such as a UUID, or it may be a universal identifier such as a DOI or a handle. In either case it must be unique across all works to be imported for the collection. This identifier will be used to identify the work in the response, and will be used to identify the work when checking for duplicate imports.

By default, the identifier is provided in the `metadata` object as an `identifiers` array with the scheme `import-recid`. E.g.,

```json
{
  "identifiers": [
    {
      "identifier": "1234567890",
      "scheme": "import-recid"
    }
    // ... other identifiers ...
  ]
}
```

To use a different scheme for deduplication, set the request form field `id_scheme` (and optionally `alternate_id_scheme`) to that scheme name, and use the same scheme in each work's `metadata.identifiers`. The scheme must already be defined in KCWorks (`RDM_RECORDS_IDENTIFIERS_SCHEMES`), or arranged with the KCWorks team for addition before import. Built-in import-oriented schemes include `import-recid` and `neh-recid`. DOI values in `pids.doi` are also used for matching when present.

(import-existing-record-files)=

### Files when re-importing an existing work (`no_updates` is `"false"`)
When an import matches an existing draft or published work and `no_updates` is `"false"` (the default), or when `no_updates` is `"true"` but metadata is unchanged so the load continues, KCWorks reconciles files against the existing record as follows:

- Same filename (key) and same size → leave the existing file; no re-upload.
- Same filename but different size, or a file still marked pending → delete the existing object and upload the new file.
- Filename present only in the import payload → upload as a new file.
- Filename present only on the existing record → delete it from the record.

Comparison is by **filename and size**, not by checksum or byte content. Two different files with the same name and size are treated as unchanged.

When `no_updates` is `"true"` and metadata **differs**, the import stops before this file step; existing files are not modified.

## Example import request
The following example shows a request to import a single work with two files and a single owner.

### Metadata JSON object
The metadata JSON string for a journal article with a PDF file and a Word file, with a single owner might look like the sample below.

```{note}
The metadata must be provided as an array of metadata objects, even if it contains only a single object.
```

```json
[
  {
    "metadata": {
      "resource_type": {
        "id": "textDocument-journalArticle"
      },
      "creators": [
        {
          "person_or_org": {
            "type": "personal",
            "name": "Fitzpatrick, Kathleen",
            "given_name": "Kathleen",
            "family_name": "Fitzpatrick",
            "identifiers": [{ "identifier": "kfitz", "scheme": "kc_username" }]
          },
          "role": { "id": "author" },
          "affiliations": [{ "name": "Modern Languages Association" }]
        }
      ],
      "title": "Giving It Away: Sharing and the Future of Scholarly Communication",
      "publisher": "University of Toronto Press Inc. (UTPress)",
      "publication_date": "2012",
      "languages": [{ "id": "eng" }],
      "identifiers": [
        { "identifier": "1234567890", "scheme": "import-recid" },
        { "identifier": "10.3138/jsp.43.4.347", "scheme": "doi" },
        { "identifier": "1710-1166", "scheme": "issn" }
      ],
      "rights": [
        {
          "id": "cc-by-4.0",
          "title": {
            "en": "Creative Commons Attribution 4.0 International"
          }
        }
      ],
      "description": "Open access has great potential to transform the future of scholarly communication, but its success will require a focus on values -- and particularly generosity -- rather than on costs."
    },
    "custom_fields": {
      "journal:journal": {
        "title": "Journal of Scholarly Publishing",
        "issue": "4",
        "volume": "43",
        "pages": "347-362",
        "issn": "1198-9742"
      },
      "kcr:user_defined_tags": ["open access", "Scholarly communication"]
    },
    "parent": {
      "owned_by": [
        {
          "full_name": "Kathleen Fitzpatrick",
          "email": "kfitz@msu.edu",
          "identifiers": [{ "identifier": "kfitz", "scheme": "kc_username" }]
        }
      ]
    },
    "files": {
      "enabled": true,
      "entries": {
        "fitzpatrick-givingitaway.docx": {
          "size": 149619,
          "key": "fitzpatrick-givingitaway.docx"
        },
        "fitzpatrick-givingitaway.pdf": {
          "size": 234567,
          "key": "fitzpatrick-givingitaway.pdf"
        }
      }
    }
  }
]
```

### HTTP request
To submit the article to be included in the `my-organization` collection, one might use a command line tool like `curl`, with the following command.

```
curl -X POST https://works.hcommons.org/api/import/my-collection-id \
  -H "Content-Type: multipart/form-data" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer <your-api-key>" \
  -F "files=@path/to/files/fitzpatrick-givingitaway.pdf" \
  -F "files=@path/to/files/fitzpatrick-givingitaway.docx" \
  -F "metadata={// ... metadata JSON object goes here as a string ... //}"
```

Of course, in most cases the request will be made programmatically, not via a command line tool. The syntax for the request will vary depending on the programming language and tools being used.

## A successful import response
```
HTTP/1.1 201 Created
Content-Type: application/json
```

This response will include a JSON object with the following fields:

- `status`: The status of the import request, which will be "success" if the import request was successful.
- `data`: An array of JSON objects, one for each record that was created in the operation
- `errors`: An array of JSON objects, one for each record that failed to be created. (In a successful import, this array will be empty.)
- `message`: A message describing the import request. (In a successful import, this will be "All records were successfully imported".)

Each object in the `data` array will have the following fields:

| key             | type      | description                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --------------- | --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `item_index`    | `integer` | The index of the record in the import request. (Starting with 0 for the first record.)                                                                                                                                                                                                                                                                                                                                                             |
| `record_id`     | `string`  | The internal KCWorks ID of the new work.                                                                                                                                                                                                                                                                                                                                                                                                           |
| `source_id`     | `string`  | The external identifier for the work that was provided in the import request using the `import-recid` scheme.                                                                                                                                                                                                                                                                                                                                      |
| `record_url`    | `string`  | The URL of the new work. This is the URL of the work's landing page on KCWorks. Other URLs for the work, including the endpoints for API operations, are available in the `links` property of the record's `metadata` object.                                                                                                                                                                                                                      |
| `files`         | `object`  | An object whose keys are the filenames for the files that were successfully uploaded and whose values are 2 member arrays. The first member is a string representing the status of the file upload operation. The second member is an array of string error messages if any errors occurred during the upload. Further details about the files, including their size and checksum, are available in the `files` property of the `metadata` object. |
| `collection_id` | `string`  | The ID of the collection to which the work was published, if any. This is provided for convenience. Details about the collection are available in the `parent.communities` property of the `metadata` object.                                                                                                                                                                                                                                      |
| `errors`        | `array`   | A list of objects, each of which describes an error that occurred during the import process. These might include validation errors for certain fields in the provided metadata that did not prevent creation of the work.                                                                                                                                                                                                                          |
| `metadata`      | `object`  | The metadata for the created work, in JSON format, following the KCWorks implementation of the InvenioRDM metadata schema described [here](https://mesh-research.github.io/knowledge-commons-works/reference/metadata.html). The returned metadata will include internal KCWorks system fields such as `created`, `updated`, `revision_id`, `id`, etc. It is identical to the metadata that would be returned by a GET request to the records API endpoint on KCWorks. |

The response object will be shaped like this:

```json
{
  "status": "success",
  "data": [
    {
      "item_index": 0,
      "record_id": "1234567890",
      "record_url": "https://works.hcommons.org/records/1234567890",
      "files": {
        "file1.pdf": ["success", []],
        "file2.pdf": ["success", []]
      },
      "collection_id": "1234567890",
      "errors": [],
      "metadata": {
        /* ... */
      }
    },
    {
      "item_index": 1,
      "record_id": "1234567891",
      "record_url": "https://works.hcommons.org/records/1234567891",
      "files": {
        "file1.pdf": ["success", []],
        "file2.pdf": ["success", []]
      },
      "collection_id": "1234567890",
      "errors": [],
      "metadata": {
        /* ... */
      }
    }
  ],
  "errors": [],
  "message": "All records were successfully imported."
}
```

## An unsuccessful import response
### The token does not have the necessary permissions
```
HTTP/1.1 403 Forbidden
Content-Type: application/json
```

This response will include a JSON object with the following fields:

```json
{
  "status": "error",
  "message": "The user does not have the necessary permissions."
}
```

### The request metadata is malformed or invalid
```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
```

This response is returned when some of the provided metadata for all of the works to be imported is malformed or invalid. This indicates that _none of the works has been created_ and a new request must be made with corrected metadata. This response will only be received if either
a. the `strict_validation` request parameter was set to "true" and all of the supplied metadata objects raise validation errors, or
b. the `strict_validation` parameter is set to "false", but the validation errors affected fields that are required for the works to be created.
c. the `all_or_none` request parameter is set to "true" and some of the supplied metadata objects raise validation errors.

The response will include a JSON object with the same shape as the successful response, but with the following differences:

- The `status` field will be "error".
- The `data` field will be an empty array.
- The `errors` field will be an array of objects, each of which describes a work that failed to be created. In each object the `record_id` and `record_url` fields will be `null`, since the work was not created. The `errors` field will be an array of objects, each of which describes an error that occurred during the attempt to create the work. The `metadata` field will still contain the metadata that was provided in the request for reference.

```json
{
    "status": "error",
    "message": (
        "No records were successfully imported. Please check the list of failed records "
        "in the 'errors' field for more information. Each failed item should have its own "
        "list of specific errors."
    ),
    "data": [],
    "errors": [
        {
            "item_index": 0,
            "record_id": null,
            "record_url": null,
            "errors": [
                {
                    "field": "title",
                    "message": "Required field missing."
                }
            ],
            "files": {},
            "collection_id": "1234567890",
            "metadata": {
                /* ... */
            }
        },
        {
            "item_index": 1,
            "record_id": null,
            "record_url": null,
            "errors": [
                {
                    "field": "metadata.creators.0.occupation",
                    "message": "Unknown field."
                },
                {
                    "field": "metadata.publication_date",
                    "message": "Date is not in Extended Date Time Format (EDTF)."
                }
            ],
            "files": {},
            "collection_id": "1234567890",
            "metadata": {
                /* ... */
            }
        }
    ]
}
```

## A partially successful import response
> NOT YET IMPLEMENTED. At present the `all_or_none` request parameter will always be "true".

If only some of the works to be imported are malformed or invalid, and the `all_or_none` request parameter is set to "false", the response will be `207 Multi-Status`. In this case the response will be shaped much like the successful and unsuccessful responses described above, but there will be items in _both_ the `data` and `errors` arrays. The items in the `data` array will be works that were successfully created, and the items in the `errors` array will be works that failed to be created.

The response will be shaped like this:

```json
{
    "status": "multi_status",
    "message": (
        "Some records were successfully imported, but some failed. Please check the "
        "list of failed records in the 'errors' field for more information. Each failed "
        "item should have its own list of specific errors."
    ),
    "data": [
        {
            "item_index": 1,
            "record_id": "1234567891",
            "source_id": "xxx1234567891",
            "record_url": "https://works.hcommons.org/records/1234567891",
            "files": {
                "file1.pdf": ["success", []],
                "file2.pdf": ["success", []]
            },
            "collection_id": "1234567890",
            "errors": [],
            "metadata": {
                /* ... */
            }
        }
    ],
    "errors": [
        {
            "item_index": 0,
            "record_id": null,
            "source_id": "xxx1234567890",
            "record_url": null,
            "errors": [
                {
                    "field": "title",
                    "message": "Required field missing."
                }
            ],
            "files": {},
            "collection_id": "1234567890",
            "metadata": {
                /* ... */
            }
        },
    ]
}
```

### The request file upload failed
```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
```

If the file content is uploaded but for some reason is considered corrupted or invalid, a `400 Bad Request` response will be returned. This response will include a JSON object with the following fields:

```json
{
    "status": "error",
    "message": (
        "No records were successfully imported. Please check the list of failed records "
        "in the 'errors' field for more information. Each failed item should have its own "
        "list of specific errors."
    ),
    "data": [],
    "errors": [
        {
            "item_index": 0,
            "record_id": null,
            "source_id": "xxx1234567890",
            "record_url": null,
            "errors": [
                {
                    "validation_error": {
                        "metadata": {"title": ["Missing data for required field."]}
                    }
                }
            ],
            "files": {
                "file1.pdf": ["uploaded", []]
            },
            "collection_id": "1234567890",
            "metadata": {
                /* ... */
            }
        },
        {
            "item_index": 1,
            "record_id": null,
            "source_id": "xxx1234567891",
            "record_url": null,
            "errors": [
                {
                    "validation_error": {
                        "metadata": {"creators" {"occupation": ["Unknown field."]}}
                    }
                },
                {
                    "validation_error": {
                        "metadata": {"publication_date": ["Date is not in Extended Date Time Format (EDTF)."]}
                    }
                },
                {
                    "file upload failures": {
                        "sample.pdf": [
                            "failed",
                            ["File sample.pdf not found in list of files."],
                        ]
                    },
                },
            ],
            "files": {
                "sample.pdf": ["failed", ["File sample.pdf not found in list of files."]],
            },
            "collection_id": "1234567890",
            "metadata": {
                /* ... */
            }
        }
    ]
}
```

If an upload simply fails to complete and times out, the client will instead receive a `504 Gateway Timeout` response.

## What happens to an import request that fails?
If all steps of an import request do not complete successfully, the work will not be created. The files that were successfully uploaded will be deleted, and any draft record created as part of the import request will be deleted. The client may attempt the import request again.

## Making duplicate import requests
Note that it is possible to make duplicate import requests _unless_ the work to be imported includes a pre-existing DOI identifier or some other unique identifier that has already been registered in KCWorks. In this case, the import request will be rejected with a `409 Conflict` response code and a `Location` header pointing to the existing work.

In the absence of such a unique identifier, however, KCWorks will not try to detect duplicate works based on the metadata, file name, or file content. If the same work is imported multiple times without a pre-existing unique identifier, it will be created multiple times in KCWorks and each version will be assigned a newly minted DOI.

