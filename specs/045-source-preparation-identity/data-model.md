# Data Model: Stable Source and Preparation Identity

## PersistedSourceRecord

- `session_id`
- `filename`: normalized working filename
- `source_token`: authoritative original-upload token
- `source_format`: `docx | doc | pdf`
- `conversion_backend`: optional provenance
- `storage_path`: confined cache path
- `payload_size`: exact stored-byte length
- `payload_digest`: digest of exact stored bytes
- `storage_kind`: `restart | completed`

Validation: non-empty token/format/path, confined path, non-empty bytes, exact size and digest match. Records missing required metadata are unavailable.

## FrozenUploadPayload

- Existing filename, bytes, size, digest, token, source format and conversion backend

Relationship: restoration maps one verified persisted record to one frozen payload without recomputing `source_token`.

## PreparationRequestIdentity

- authoritative source token
- chunk size
- processing operation
- canonical source language
- canonical target language

Validation: equivalent language spellings normalize identically; any semantic axis change changes identity.

## State transitions

`normalized payload → persist metadata+bytes → verify metadata+bytes → restore frozen payload → prepare without conversion`

`missing/corrupt record → unavailable → clear/ignore cache → fresh upload required`
